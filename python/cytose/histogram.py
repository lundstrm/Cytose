"""Full-event histogram calculations shared by worksheet and overlays."""
from __future__ import annotations
import numpy as np
from .core import membership, population_available, transform


def histogram_series(samples, gates, population, parameter, logarithmic, *, bins=80, bounds=None, normalized=False):
    """Return transformed bin edges, per-sample counts, and unavailable sample names.

    Gates are a list shared by all samples or a function returning each sample's gates.

    Normalized heights are percentages of all finite gated events; events outside a
    manually selected display range are counted in the first or last bin.
    """
    gates_of=gates if callable(gates) else (lambda sample:gates)
    arrays=[]; missing=[]
    for sample in samples:
        names=[p.name for p in sample.parameters]
        if names.count(parameter)!=1 or not population_available(sample,gates_of(sample),population):
            missing.append(sample.name); continue
        values=transform(sample.events[membership(sample,gates_of(sample),population),names.index(parameter)],logarithmic)
        arrays.append((sample,values[np.isfinite(values)]))
    if bounds is None:
        nonempty=[values for _,values in arrays if len(values)]
        lo=min((float(values.min()) for values in nonempty),default=0.)
        hi=max((float(values.max()) for values in nonempty),default=1.)
        if hi<=lo: hi=lo+1.
    else:
        lo,hi=map(float,bounds)
        if not np.isfinite(lo) or not np.isfinite(hi) or hi<=lo: raise ValueError('Invalid histogram range')
    edges=np.linspace(lo,hi,bins+1); series=[]
    for sample,values in arrays:
        counts=np.histogram(np.clip(values,lo,hi),bins=edges)[0].astype(float)  # out-of-range events land in the edge bins
        if normalized and len(values): counts*=100./len(values)
        series.append((sample,counts))
    return edges,series,missing


def scatter_series(samples, gates, population, x, y, logx, logy, *, bins=256, bounds=None):
    """Return shared transformed bounds, per-sample 2D counts, and unavailable sample names.

    Bounds span the central 99.8% of pooled events so rare outliers do not
    compress the display; statistics elsewhere still use every event. Count
    rows run from the top of the plot down, ready for image display. Explicit
    bounds (a zoomed view) replace the automatic range.
    """
    gates_of=gates if callable(gates) else (lambda sample:gates)
    arrays=[]; missing=[]
    for sample in samples:
        names=[p.name for p in sample.parameters]
        if names.count(x)!=1 or names.count(y)!=1 or not population_available(sample,gates_of(sample),population):
            missing.append(sample.name); continue
        values=sample.events[membership(sample,gates_of(sample),population)]
        vx=transform(values[:,names.index(x)],logx); vy=transform(values[:,names.index(y)],logy); valid=np.isfinite(vx)&np.isfinite(vy)
        arrays.append((sample,vx[valid],vy[valid]))
    automatic=[]
    for k in (1,2):
        pooled=np.concatenate([item[k] for item in arrays]) if arrays else np.array([])
        lo,hi=(float(v) for v in np.percentile(pooled,[0.1,99.9])) if len(pooled) else (0.,1.)
        pad=0.02*(hi-lo); automatic.append((lo-pad,hi+pad) if hi>lo else (lo-0.5,lo+0.5))
    bounds=[tuple(map(float,axis)) for axis in bounds] if bounds is not None else automatic
    (a,b),(c,d)=bounds
    series=[(sample,np.histogram2d(np.clip(vx,a,b),np.clip(vy,c,d),bins=bins,range=[[a,b],[c,d]])[0].T[::-1]) for sample,vx,vy in arrays]  # edges collect out-of-range events
    return bounds,series,missing


def smooth(counts, sigma=1.5):
    """Gaussian-smooth a 2D count grid for display; the total is preserved away from the edges."""
    radius=max(1,int(round(3*sigma))); offsets=np.arange(-radius,radius+1)
    kernel=np.exp(-offsets**2/(2*sigma**2)); kernel/=kernel.sum()
    rows=np.apply_along_axis(lambda line:np.convolve(line,kernel,mode='same'),1,np.asarray(counts,dtype=float))
    return np.apply_along_axis(lambda line:np.convolve(line,kernel,mode='same'),0,rows)


def probability_levels(density, fractions):
    """Density thresholds whose enclosed regions hold the given fractions of the total."""
    flat=np.sort(np.asarray(density,dtype=float).ravel())[::-1]; total=flat.sum()
    if total<=0: return []
    cumulative=np.cumsum(flat)/total
    return [float(flat[min(len(flat)-1,int(np.searchsorted(cumulative,fraction)))]) for fraction in fractions]


# Marching-squares edges per corner case (top-left 8, top-right 4, bottom-right 2, bottom-left 1);
# edges are 0 top, 1 right, 2 bottom, 3 left.
_CASES={1:[(3,2)],2:[(2,1)],3:[(3,1)],4:[(0,1)],5:[(0,1),(3,2)],6:[(0,2)],7:[(0,3)],8:[(0,3)],9:[(0,2)],10:[(0,3),(2,1)],11:[(0,1)],12:[(3,1)],13:[(2,1)],14:[(3,2)]}


def contour_segments(grid, level):
    """Return isoline segments as an (N, 4) array of (column, row) start and end points."""
    g=np.asarray(grid,dtype=float); tl,tr,br,bl=g[:-1,:-1],g[:-1,1:],g[1:,1:],g[1:,:-1]
    case=(tl>=level)*8+(tr>=level)*4+(br>=level)*2+(bl>=level)*1
    rows,cols=np.mgrid[0:g.shape[0]-1,0:g.shape[1]-1].astype(float)
    with np.errstate(divide='ignore',invalid='ignore'):
        fraction=lambda a,b:np.clip(np.nan_to_num((level-a)/(b-a),nan=.5,posinf=.5,neginf=.5),0,1)
        edges=[(cols+fraction(tl,tr),rows),(cols+1,rows+fraction(tr,br)),(cols+fraction(bl,br),rows+1),(cols,rows+fraction(tl,bl))]
    segments=[]
    for value,pairs in _CASES.items():
        mask=case==value
        if not mask.any(): continue
        for first,second in pairs:
            segments.append(np.column_stack([edges[first][0][mask],edges[first][1][mask],edges[second][0][mask],edges[second][1][mask]]))
    return np.vstack(segments) if segments else np.zeros((0,4))
