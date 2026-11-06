import csv
import io
import struct
import tempfile
import unittest
import weakref
import gc
from unittest.mock import Mock
from pathlib import Path
import numpy as np
from cytose.core import FCSError, Gate, Parameter, Sample, StatisticsCache, condition_name, default_gate_name, export_csv, membership, natural_key, read_fcs, save_json, statistics
from cytose.core import compensate, spillover_from_controls, spillover_from_metadata
from cytose.histogram import contour_segments, histogram_series, probability_levels, scatter_series, smooth


def fixture(path, endian='<', kind='F'):
    names=['FSC-A','SSC-A']; values=[(1.,2.),(3.,4.),(5.,6.)]
    typ='f' if kind=='F' else 'H'; bits=32 if kind=='F' else 16
    data=b''.join(struct.pack(endian+typ*2,*([int(v) for v in row] if kind=='I' else row)) for row in values)
    order='1,2,3,4' if endian=='<' else '4,3,2,1'
    text=f'|$MODE|L|$PAR|2|$TOT|3|$DATATYPE|{kind}|$BYTEORD|{order}|$P1N|{names[0]}|$P1B|{bits}|$P2N|{names[1]}|$P2B|{bits}|$NEXTDATA|0|'.encode()
    ts=58; te=ts+len(text)-1; ds=te+1; de=ds+len(data)-1
    header=b'FCS3.1    '+b''.join(f'{n:8d}'.encode() for n in (ts,te,ds,de,0,0))
    path.write_bytes(header+text+data)



def multichannel_fixture(path, names, rows, extra=''):
    """FCS 3.1 float file with arbitrary channels and optional extra TEXT keywords ('|KEY|value')."""
    data=b''.join(struct.pack('<'+'f'*len(names),*row) for row in rows)
    text='|$MODE|L|$PAR|%d|$TOT|%d|$DATATYPE|F|$BYTEORD|1,2,3,4|'%(len(names),len(rows))+''.join(f'$P{i}N|{n}|$P{i}B|32|' for i,n in enumerate(names,1))+'$NEXTDATA|0|'+extra
    text=text.encode(); ts=58; te=ts+len(text)-1; ds=te+1; de=ds+len(data)-1
    path.write_bytes(b'FCS3.1    '+b''.join(f'{n:8d}'.encode() for n in (ts,te,ds,de,0,0))+text+data)

class CoreTests(unittest.TestCase):
    def test_parse_encodings(self):
        with tempfile.TemporaryDirectory() as d:
            for endian in ('<','>'):
                for kind in ('F','I'):
                    path=Path(d)/'sample.fcs'; fixture(path,endian,kind); sample=read_fcs(path)
                    np.testing.assert_array_equal(sample.events,[[1,2],[3,4],[5,6]])
                    self.assertFalse(sample.events.flags.writeable)
    def test_malformed(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bad.fcs'; path.write_bytes(b'bad')
            with self.assertRaises(FCSError): read_fcs(path)
    def test_nested_stats_and_boundary(self):
        s=Sample('x.fcs',{},[Parameter('X'),Parameter('Y')],np.array([[0.,0.],[1.,1.],[2.,2.],[3.,3.]]))
        a=Gate('A','X','Y',[[0,0],[2,0],[2,2],[0,2]])
        b=Gate('B','X','Y',[[1,1],[3,1],[3,3],[1,3]],a.id)
        self.assertEqual(membership(s,[a,b],b.id).tolist(),[False,True,True,False])
        stats=statistics(s,[a,b],b.id,'X'); self.assertEqual(stats['count'],2); self.assertAlmostEqual(stats['percent_parent'],200/3); self.assertEqual(stats['median'],1.5)
    def test_cached_membership_follows_gate_and_parent_edits(self):
        s=Sample('x',{},[Parameter('X'),Parameter('Y')],np.array([[0.,0.],[1.,1.],[2.,2.],[3.,3.],[np.nan,1.]]))
        parent=Gate('P','X','Y',[[0,0],[3,0],[3,3],[0,3]]); child=Gate('C','X','Y',[[1,1],[3,1],[3,3],[1,3]],parent.id)
        first=membership(s,[parent,child],child.id); self.assertEqual(first.tolist(),[False,True,True,True,False]); self.assertFalse(first.flags.writeable)
        self.assertIs(membership(s,[parent,child],child.id),first)
        parent.vertices=[[0,0],[2,0],[2,2],[0,2]]; self.assertEqual(membership(s,[parent,child],child.id).tolist(),[False,True,True,False,False])
        child.vertices=[[1.5,1.5],[3,1.5],[3,3],[1.5,3]]; self.assertEqual(membership(s,[parent,child],child.id).tolist(),[False,False,True,False,False])
        self.assertEqual(membership(s,[child],child.id).tolist(),[False]*5)
    def test_tilted_quadrants_partition_events(self):
        s=Sample('x',{},[Parameter('X'),Parameter('Y')],np.array([[1.,3.],[3.,3.],[3.,1.],[1.,1.],[2.6,2.4],[2.3,2.8]]))
        gates=[Gate(f'q{x}{y}','X','Y',[],quadrant=[2,2,x,y],spokes=[[3,4],[4,2],[2,0],[0,2]]) for x in (False,True) for y in (False,True)]
        masks={(g.quadrant[2],g.quadrant[3]):membership(s,gates,g.id) for g in gates}
        self.assertEqual(sum(m.astype(int) for m in masks.values()).tolist(),[1]*6)
        # (2.3, 2.8) is right of the old vertical line but left of the tilted top spoke towards (3, 4).
        self.assertTrue(masks[(False,True)][5]); self.assertFalse(masks[(True,True)][5]); self.assertTrue(masks[(True,True)][4])
    def test_compensation_recovers_signals_and_estimates_spillover(self):
        rng=np.random.default_rng(1); true=np.column_stack([rng.uniform(0,10,500),rng.uniform(0,1000,500),rng.uniform(0,1000,500)])
        spill=np.array([[1.,.1],[.05,1.]]); raw=true.copy(); raw[:,1:]=true[:,1:]@spill
        names=[Parameter('FSC-A'),Parameter('FL1-A'),Parameter('FL2-A')]; s=Sample('s',{},names,raw)
        fixed=compensate(s,['FL1-A','FL2-A'],spill); np.testing.assert_allclose(fixed,true,atol=1e-6); self.assertFalse(fixed.flags.writeable)
        self.assertIs(compensate(s,['FL1-A','FL9-A'],spill),raw)
        signal=rng.uniform(100,10000,2000); control=Sample('c',{},names,np.column_stack([np.ones(2000),signal,0.1*signal+50]))
        unstained=Sample('u',{},names,np.column_stack([np.ones(2000),np.zeros(2000),np.full(2000,50.)]))
        estimate=spillover_from_controls([control,unstained],{'c':'FL1','u':'unstained'},['FL1-A','FL2-A'])
        self.assertAlmostEqual(estimate[0,1],0.1,places=2); self.assertEqual(estimate[1,0],0.); self.assertEqual(estimate[1,1],1.)
        names_,matrix=spillover_from_metadata({'$SPILLOVER':'2,FL1-A,FL2-A,1,0.2,0.03,1'}); self.assertEqual(names_,['FL1-A','FL2-A']); self.assertEqual(matrix[0,1],0.2)
        self.assertIsNone(spillover_from_metadata({}))
    def test_quadrant_partition(self):
        s=Sample('x',{},[Parameter('X'),Parameter('Y')],np.array([[0.,0.],[1,0],[0,1],[1,1]]))
        gates=[Gate('q','X','Y',[],quadrant=[0,0,x,y]) for x in (False,True) for y in (False,True)]
        self.assertEqual(sum(int(membership(s,gates,g.id).sum()) for g in gates),4)
    def test_missing_gate_channel_is_not_reported_as_zero(self):
        s=Sample('x',{},[Parameter('X')],np.array([[1.],[2.]]))
        gate=Gate('A','X','Y',[[0,0],[1,0],[1,1]])
        self.assertIsNone(statistics(s,[gate],gate.id,'X')['percent_parent'])
        self.assertIsNone(statistics(s,[gate],gate.id,'X')['count'])
    def test_statistics_cache_updates_for_nested_gate_changes_and_does_not_retain_samples(self):
        s=Sample('x',{},[Parameter('X'),Parameter('Y')],np.array([[0.,0.],[1.,1.],[2.,2.],[3.,3.]]))
        parent=Gate('parent','X','Y',[[0,0],[2,0],[2,2],[0,2]])
        child=Gate('child','X','Y',[[1,1],[3,1],[3,3],[1,3]],parent.id)
        calculate=Mock(wraps=statistics); cache=StatisticsCache(capacity=2,calculator=calculate)
        self.assertEqual(cache.get(s,[parent,child],child.id,'X')['count'],2)
        self.assertEqual(cache.get(s,[parent,child],child.id,'X')['median'],1.5); self.assertEqual(calculate.call_count,1)
        parent.vertices=[[0,0],[1,0],[1,1],[0,1]]
        self.assertEqual(cache.get(s,[parent,child],child.id,'X')['count'],1); self.assertEqual(calculate.call_count,2)
        child.vertices=[[2,2],[3,2],[3,3],[2,3]]
        self.assertEqual(cache.get(s,[parent,child],child.id,'X')['count'],0); self.assertEqual(calculate.call_count,3)
        self.assertLessEqual(len(cache.entries),2)
        sample_ref=weakref.ref(s); event_ref=weakref.ref(s.events); calculate.reset_mock(); del s; gc.collect()
        self.assertIsNone(sample_ref()); self.assertIsNone(event_ref())
    def test_overlay_series_share_bounds_and_report_unavailable_samples(self):
        a=Sample('a.fcs',{},[Parameter('X'),Parameter('Y')],np.array([[1.,10.],[2.,20.],[3.,30.],[4.,np.nan]]))
        b=Sample('b.fcs',{},[Parameter('X'),Parameter('Y')],np.array([[5.,50.],[6.,60.]]))
        c=Sample('c.fcs',{},[Parameter('X')],np.array([[1.]]))
        gate=Gate('low','X','Y',[[0,0],[5.5,0],[5.5,100],[0,100]])
        bounds,series,missing=scatter_series([a,b,c],[gate],gate.id,'X','Y',False,False,bins=4)
        (lo,hi),(bottom,top)=bounds; self.assertTrue(lo<1<5<hi and bottom<10<50<top); self.assertEqual(missing,['c.fcs'])
        self.assertEqual([sample.name for sample,_ in series],['a.fcs','b.fcs']); self.assertEqual([int(counts.sum()) for _,counts in series],[3,1])
        self.assertEqual(series[1][1][0,-1],1)
        outlier=Sample('o.fcs',{},[Parameter('X'),Parameter('Y')],np.vstack([np.column_stack([np.linspace(0,10,2000)]*2),[[1e6,1e6]]]))
        (lo,hi),_=scatter_series([outlier],[],None,'X','Y',False,False)[0]; self.assertLess(hi,11)
        edges,series,missing=histogram_series([a,b],[],None,'X',False,bins=5,normalized=True)
        self.assertEqual((edges[0],edges[-1]),(1.,6.)); self.assertEqual(missing,[])
        for _,counts in series: self.assertAlmostEqual(counts.sum(),100.)
    def test_contours_enclose_requested_probability(self):
        rows,cols=np.mgrid[0:41,0:41]; blob=np.exp(-((rows-20)**2+(cols-20)**2)/50.)
        self.assertAlmostEqual(smooth(blob).sum()/blob.sum(),1.,places=3)
        inner,outer=probability_levels(blob,[0.5,0.95]); self.assertGreater(inner,outer)
        self.assertAlmostEqual(blob[blob>=outer].sum()/blob.sum(),0.95,delta=0.02)
        segments=contour_segments(blob,outer); radius=np.hypot(segments[:,0]-20,segments[:,1]-20)
        self.assertGreater(len(segments),20); self.assertLess(radius.max()-radius.min(),1.)
        self.assertEqual(contour_segments(blob,10.).shape,(0,4))
    def test_default_gate_names(self):
        self.assertEqual(default_gate_name('FSC-A','SSC-A',[]),'Cells')
        self.assertEqual(default_gate_name('SSC-A','FSC-H',['Cells']),'Cells 2')
        self.assertEqual(default_gate_name('FSC-A','FSC-H',[]),'Singlets'); self.assertEqual(default_gate_name('SSC-W','SSC-A',[]),'Singlets')
        self.assertEqual(default_gate_name('FL1-A','SSC-A',['G1','Q1']),'G2'); self.assertEqual(default_gate_name('FL1-A','FL2-A',['G2']),'G1')
    def test_out_of_range_events_collect_on_edges(self):
        s=Sample('s.fcs',{},[Parameter('X'),Parameter('Y')],np.array([[-5.,-5.],[1.,1.],[2.,2.],[50.,50.]]))
        edges,series,_=histogram_series([s],[],None,'X',False,bins=4,bounds=(0,4)); counts=series[0][1]
        self.assertEqual(counts.tolist(),[1,1,1,1])  # -5 lands in the first bin, 50 in the last
        _,series,_=scatter_series([s],[],None,'X','Y',False,False,bins=4,bounds=[(0,4),(0,4)]); grid=series[0][1]
        self.assertEqual(grid.sum(),4); self.assertEqual(grid[-1,0],1); self.assertEqual(grid[0,-1],1)
    def test_csv_and_names(self):
        self.assertEqual(condition_name('A01 A375.fcs'),'A375')
        self.assertEqual(sorted(['b1.fcs','A10.fcs','a2.fcs'],key=natural_key),['a2.fcs','A10.fcs','b1.fcs'])
        self.assertEqual(condition_name('AA048_A375.fcs'),'A375')
        self.assertEqual(condition_name('A49 A375.fcs'),'A49 A375')
        result=export_csv([['sample','value'],['a,b',2]])
        self.assertEqual(list(csv.reader(io.StringIO(result))),[['sample','value'],['a,b','2']])
    def test_atomic_save(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a.cytose'; save_json(path,{'value':3}); self.assertIn('3',path.read_text())
    def test_included_fcs(self):
        root=Path(__file__).resolve().parents[2]/'fcs_examples'
        files=list(root.rglob('*.fcs'))
        if not files: self.skipTest('No bundled sample files')
        s=read_fcs(files[0]); self.assertGreater(len(s.events),0); self.assertGreater(len(s.parameters),1)

if __name__=='__main__': unittest.main()
