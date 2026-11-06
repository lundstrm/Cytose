"""Editable multi-sample overlays; FCS events remain in their samples."""
from __future__ import annotations
import json
import uuid
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QLineF, QMimeData, QRectF, QPointF, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QPolygonF, QPixmap, QIcon
from PySide6.QtWidgets import (QApplication, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton, QVBoxLayout, QWidget)
from .core import export_csv
from .dialogs import add_done, remembered, start_folder
from .histogram import contour_segments, histogram_series, probability_levels, scatter_series, smooth
from .plot import DARK_WORKSHEET_BACKGROUND, LIGHT_WORKSHEET_BACKGROUND, axis_ticks, choice_menu, draw_choice_icon, log_scale, log_tick_label, positioned_tick_labels, tick_font, tick_label

COLORS=['#c23537','#0385ae','#058f60','#a15989','#ef6130','#9f6d55','#fcc326','#91d3e3']
SAMPLE_MIME='application/x-cytose-samples'
CONTROLS=('kind','scale','style','offset','levels','opacity')
DEFAULTS={'offset':0.,'opacity':0.6,'levels':5}
BARS={'offset':(0.,1.,'Offset',lambda v:f'{round(v*100)}%'),'opacity':(0.05,1.,'Opacity',lambda v:f'{round(v*100)}%'),'levels':(2,10,'Levels',lambda v:str(int(v)))}


def sample_mime(paths):
    mime=QMimeData(); mime.setData(SAMPLE_MIME,json.dumps(list(paths)).encode()); return mime


def dragged_paths(mime):
    if not mime.hasFormat(SAMPLE_MIME): return []
    try: paths=json.loads(bytes(mime.data(SAMPLE_MIME)).decode())
    except ValueError: return []
    return [path for path in paths if isinstance(path,str)] if isinstance(paths,list) else []


def new_overlay(name,paths,x,y='SSC-A',population=None):
    entries=[{'path':path,'color':COLORS[i%len(COLORS)],'visible':True} for i,path in enumerate(dict.fromkeys(paths))]
    return {'id':str(uuid.uuid4()),'name':name,'kind':'histogram','x':x,'y':y,'population':population,'offset':0.,'scale':'count','style':'density','levels':5,'opacity':0.6,'zoom':None,'entries':entries}


def add_entries(overlay,paths):
    """Append samples not already in the overlay, using the next unused palette colors."""
    present={e['path'] for e in overlay['entries']}; added=[]
    for path in dict.fromkeys(paths):
        if path in present: continue
        used={e['color'] for e in overlay['entries']}
        color=next((c for c in COLORS if c not in used),COLORS[len(overlay['entries'])%len(COLORS)])
        overlay['entries'].append({'path':path,'color':color,'visible':True}); present.add(path); added.append(path)
    return added


def paint_drop_cue(widget,rect,text,dark):
    """Highlight a drop target with a short description of what dropping will do."""
    accent=QColor('#287af4' if dark else '#286ac9')
    painter=QPainter(widget); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(accent,2)); fill=QColor(accent); fill.setAlpha(40); painter.setBrush(fill); painter.drawRoundedRect(QRectF(rect).adjusted(1,1,-1,-1),5,5)
    metrics=QFontMetricsF(painter.font()); width=metrics.horizontalAdvance(text)+14; height=metrics.height()+6
    pill=QRectF(rect.right()-width-6,rect.center().y()-height/2,width,height)
    painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(accent); painter.drawRoundedRect(pill,height/2,height/2)
    painter.setPen(QColor('white')); painter.drawText(pill,Qt.AlignmentFlag.AlignCenter,text); painter.end()


def swatch(color,size=12):
    square=QPixmap(size,size); square.fill(QColor(color)); return QIcon(square)


class SampleChooser(QDialog):
    """Pick several samples at once, optionally naming the overlay that will hold them."""
    def __init__(self,parent,title,samples,checked=(),name=None):
        super().__init__(parent); self.setWindowTitle(title); layout=QVBoxLayout(self); layout.setContentsMargins(18,16,18,14); layout.setSpacing(6); self.name=None
        if name is not None:
            layout.addWidget(QLabel('Name')); self.name=QLineEdit(name); layout.addWidget(self.name)
        layout.addWidget(QLabel('Samples'))
        self.list=QListWidget(); self.list.setMinimumSize(320,260)
        for sample in samples:
            item=QListWidgetItem(sample.name); item.setData(Qt.ItemDataRole.UserRole,sample.path); item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if sample.path in checked else Qt.CheckState.Unchecked); self.list.addItem(item)
        self.list.itemDoubleClicked.connect(lambda item:item.setCheckState(Qt.CheckState.Unchecked if item.checkState()==Qt.CheckState.Checked else Qt.CheckState.Checked))
        layout.addWidget(self.list,1)
        row=QHBoxLayout(); every=QPushButton('Select all'); none=QPushButton('Clear'); row.addWidget(every); row.addWidget(none); row.addStretch(); layout.addLayout(row)
        every.clicked.connect(lambda:self.set_all(True)); none.clicked.connect(lambda:self.set_all(False))
        add_done(self,layout)
    def set_all(self,checked):
        for i in range(self.list.count()): self.list.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
    def paths(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count()) if self.list.item(i).checkState()==Qt.CheckState.Checked]


class OverlayList(QListWidget):
    """File Browser overlays; dropping samples adds to an overlay or creates a new one."""
    def __init__(self,ws):
        super().__init__(); self.ws=ws; self.drop_row=None; self.drop_new=False; self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.customContextMenuRequested.connect(self.menu)
    def overlay_id(self,item): return item.data(Qt.ItemDataRole.UserRole) if item else None
    def dragEnterEvent(self,e):
        if dragged_paths(e.mimeData()): e.acceptProposedAction()
        else: e.ignore()
    def dragMoveEvent(self,e):
        if not dragged_paths(e.mimeData()): e.ignore(); return
        item=self.itemAt(e.position().toPoint()); self.drop_row=self.row(item) if item else None; self.drop_new=item is None
        e.acceptProposedAction(); self.viewport().update()
    def dragLeaveEvent(self,e):
        self.drop_row=None; self.drop_new=False; self.viewport().update()
    def dropEvent(self,e):
        paths=dragged_paths(e.mimeData()); item=self.itemAt(e.position().toPoint()); self.drop_row=None; self.drop_new=False; self.viewport().update()
        if not paths: e.ignore(); return
        if item: self.ws.add_to_overlay(self.overlay_id(item),paths)
        else: self.ws.create_overlay(paths)
        e.acceptProposedAction()
    def paintEvent(self,e):
        super().paintEvent(e)
        if self.drop_row is not None and self.item(self.drop_row):
            paint_drop_cue(self.viewport(),self.visualItemRect(self.item(self.drop_row)),'Add to overlay',self.ws.dark)
        elif self.drop_new:
            paint_drop_cue(self.viewport(),self.viewport().rect(),'Create overlay',self.ws.dark)
        elif not self.count():
            painter=QPainter(self.viewport()); painter.setPen(QColor('#99999e' if self.ws.dark else '#73736d'))
            painter.drawText(QRectF(self.viewport().rect()).adjusted(6,4,-6,-4),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,'Drag a sample onto another sample to overlay them'); painter.end()
    def menu(self,pos):
        oid=self.overlay_id(self.itemAt(pos)); menu=QMenu(self)
        if oid:
            menu.addAction('Rename',lambda:self.ws.rename_overlay(oid)); menu.addAction('Duplicate',lambda:self.ws.duplicate_overlay(oid)); menu.addAction('Delete',lambda:self.ws.remove_overlay(oid)); menu.addSeparator()
        menu.addAction('New overlay…',self.ws.new_overlay_dialog); menu.exec(self.viewport().mapToGlobal(pos))


class OverlayGraph(QWidget):
    """Square overlay figure; titles and switches choose what is plotted, like the analysis plot."""
    def __init__(self,view):
        super().__init__(); self.view=view; self.setMinimumSize(300,300); self.setMouseTracking(True); self.setFocusPolicy(Qt.FocusPolicy.ClickFocus); self.data=None; self.drop_hint=False; self.exporting=False
        self.drag_start=None; self.drag_end=None; self.bar_drag=None; self.switch_pos={}; self.zoom_stack=[]
        self.switch_timer=QTimer(self); self.switch_timer.setInterval(16); self.switch_timer.timeout.connect(self.animate_switches)
    def recompute(self):
        ws=self.view.ws; overlay=self.view.overlay
        if not overlay or not overlay.get('x'):
            self.data=None; self.update(); return
        by_path={sample.path:sample for sample in ws.samples}; visible=[e for e in overlay['entries'] if e.get('visible',True)]
        samples=[by_path[e['path']] for e in visible if e['path'] in by_path]
        missing=[Path(e['path']).name for e in visible if e['path'] not in by_path]
        colors={e['path']:e['color'] for e in overlay['entries']}; x=overlay['x']; zoom=overlay.get('zoom')
        if overlay.get('kind')=='scatter':
            y=overlay.get('y') or x; contour=overlay.get('style')=='contour'
            bounds,series,unavailable=scatter_series(samples,ws.gates_for,overlay.get('population'),x,y,log_scale(x),log_scale(y),bins=128 if contour else 256,bounds=zoom if zoom and zoom[1] else None)
            if contour:
                # Equal-probability contours: the outer line encloses 95% of each sample's plotted events.
                levels=max(2,min(10,int(overlay.get('levels',5)))); fractions=[0.95*(i+1)/levels for i in range(levels)]; layers=[]
                for sample,counts in series:
                    # Fewer events in view (e.g. when zoomed) need wider smoothing to keep lines smooth.
                    density=smooth(counts,float(np.clip(2.5*np.sqrt(20000/max(counts.sum(),1.)),2.5,6.)))
                    layers.append((colors.get(sample.path,COLORS[0]),[contour_segments(density,t) for t in probability_levels(density,fractions) if t>0],counts.shape))
                self.data=('contour',bounds,layers,missing+unavailable); self.update(); return
            alpha=self.bar_value('opacity'); layers=[]
            for sample,counts in series:
                maximum=counts.max()
                if not maximum: continue
                intensity=np.log1p(counts)/np.log1p(maximum); color=QColor(colors.get(sample.path,COLORS[0]))
                rgba=np.zeros(counts.shape+(4,),dtype=np.uint8); rgba[...,0]=color.red(); rgba[...,1]=color.green(); rgba[...,2]=color.blue()
                rgba[...,3]=np.where(counts>0,255*alpha*(0.35+0.65*intensity),0).astype(np.uint8)
                layers.append(QImage(rgba.data,rgba.shape[1],rgba.shape[0],4*rgba.shape[1],QImage.Format.Format_RGBA8888).copy())
            self.data=('scatter',bounds,layers,missing+unavailable)
        else:
            edges,series,unavailable=histogram_series(samples,ws.gates_for,overlay.get('population'),x,log_scale(x),bounds=zoom[0] if zoom else None)
            if overlay.get('scale')=='modal': series=[(sample,counts*100./counts.max() if counts.max() else counts) for sample,counts in series]
            maximum=max((float(counts.max()) for _,counts in series if len(counts)),default=0.) or 1.
            self.data=('histogram',[(float(edges[0]),float(edges[-1])),(0.,maximum*1.1)],[(colors.get(sample.path,COLORS[0]),edges,counts,sample.name) for sample,counts in series],missing+unavailable)
        self.update()
    def layout_origin(self):
        """Centre the control column and the square plot (with its axis margin) as one group."""
        gap=36; margin=96; scale={1:1.,2:.92,3:.85,4:.75,5:.65}.get(self.view.ws.plot_columns,.85); side=max(1.,scale*min(self.width()-170-gap-margin-22,self.height()-116))
        left=max(8.,(self.width()-(170+gap+margin+side))/2); return left,left+170+gap+margin,side
    def plot_rect(self):
        _,left,side=self.layout_origin(); return QRectF(left,52+max(0.,(self.height()-116-side)/2),side,side)
    def control_rects(self):
        """Active switches, then active bars, beside the plot; slots are fixed so Opacity always sits at the bottom."""
        keys=[key for key in CONTROLS if self.control_active(key)]; switches=[k for k in keys if k not in BARS]; bars=[k for k in keys if k in BARS]
        rect=self.plot_rect(); x=self.layout_origin()[0]; top=rect.center().y()-(2*28+8+14+2*30+8)/2; rects={}
        for i,key in enumerate(switches): rects[key]=QRectF(x,top+i*36,170,28)
        bottom=top+2*28+8+14+2*30+8
        for i,key in enumerate(reversed(bars)): rects[key]=QRectF(x,bottom-30-i*38,170,30)
        return rects
    def control_active(self,key):
        overlay=self.view.overlay or {}; scatter=overlay.get('kind')=='scatter'
        return {'kind':True,'scale':not scatter,'style':scatter,'offset':not scatter,'opacity':True,'levels':scatter and overlay.get('style')=='contour'}[key]
    def title_rect(self,rect):
        return QRectF(rect.left(),rect.top()-44,rect.width(),28)
    def x_title_rect(self,rect): return QRectF(rect.left(),rect.bottom()+24,rect.width(),24)
    def y_title_rect(self,rect):
        return QRectF(rect.left()-84,rect.top(),30,rect.height())
    def scatter(self):
        overlay=self.view.overlay; return bool(overlay) and overlay.get('kind')=='scatter'
    def lane_layout(self,rect,count):
        """Baselines for histogram lanes: offset 0 overlays every sample, 1 gives each its own lane."""
        offset=float(np.clip(self.view.overlay.get('offset',0.) if self.view.overlay else 0.,0.,1.))
        height=rect.height()/(1+offset*max(0,count-1))
        return offset,height,lambda i:rect.top()+height+i*offset*height
    def switch_targets(self):
        overlay=self.view.overlay or {}
        return {'kind':1. if overlay.get('kind')=='scatter' else 0.,'scale':1. if overlay.get('scale')=='modal' else 0.,'style':1. if overlay.get('style')=='contour' else 0.}
    def animate_switches(self):
        targets=self.switch_targets(); settled=True
        for key,target in targets.items():
            pos=self.switch_pos.get(key,target); pos+=(target-pos)*0.35
            if abs(target-pos)<0.01: pos=target
            else: settled=False
            self.switch_pos[key]=pos
        if settled: self.switch_timer.stop()
        self.update()
    def paint_switch(self,painter,rect,labels,position,vertical,light):
        painter.save(); painter.setPen(QPen(QColor('#b0afa8' if light else '#414145'),1)); painter.setBrush(QColor('#d4d3cd' if light else '#252528')); painter.drawRoundedRect(rect,6,6)
        half=(rect.height() if vertical else rect.width())/2
        selected=QRectF(rect.left()+2,rect.top()+2+position*half,rect.width()-4,half-4) if vertical else QRectF(rect.left()+2+position*half,rect.top()+2,half-4,rect.height()-4)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor('#365c82')); painter.drawRoundedRect(selected,4,4)
        for index,label in enumerate(labels):
            painter.setPen(QColor('#eeeeee' if abs(position-index)<0.5 else '#70706a' if light else '#858589'))
            if vertical:
                painter.save(); painter.translate(rect.center().x(),rect.top()+(index+.5)*half); painter.rotate(-90)
                painter.drawText(QRectF(-half/2,-rect.width()/2,half,rect.width()),Qt.AlignmentFlag.AlignCenter,label); painter.restore()
            else: painter.drawText(QRectF(rect.left()+index*half,rect.top(),half,rect.height()),Qt.AlignmentFlag.AlignCenter,label)
        painter.restore()
    def bar_value(self,key):
        low,high,_,_=BARS[key]; return float(np.clip((self.view.overlay or {}).get(key,DEFAULTS[key]),low,high))
    def paint_bar(self,painter,rect,key,light):
        """A slider styled like the switches: the filled part shows the value."""
        low,high,label,text=BARS[key]; value=self.bar_value(key); fraction=(value-low)/(high-low)
        painter.save(); painter.setPen(QPen(QColor('#b0afa8' if light else '#414145'),1)); painter.setBrush(QColor('#d4d3cd' if light else '#252528')); painter.drawRoundedRect(rect,6,6)
        inner=rect.adjusted(2,2,-2,-2); painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor('#365c82'))
        if fraction>0: painter.drawRoundedRect(QRectF(inner.left(),inner.top(),max(8.,inner.width()*fraction),inner.height()),4,4)
        painter.setPen(QColor('#eeeeee' if fraction>0.3 or not light else '#292929')); painter.drawText(inner.adjusted(8,0,-8,0),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,label)
        painter.setPen(QColor('#292929' if light else '#eeeeee')); painter.drawText(inner.adjusted(8,0,-8,0),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,text(value))
        painter.restore()
    def paint_controls(self,painter,positions,light):
        labels={'kind':('Histogram','Scatter'),'scale':('Count','Modal'),'style':('Density','Contour')}
        for key,rect in self.control_rects().items():
            if key in labels: self.paint_switch(painter,rect,labels[key],positions[key],False,light)
            else: self.paint_bar(painter,rect,key,light)
    def set_bar(self,key,value,checkpoint=True):
        low,high,_,_=BARS[key]; value=float(np.clip(value,low,high)); value=int(round(value)) if key=='levels' else round(value,2)
        overlay=self.view.overlay
        if not overlay or overlay.get(key,DEFAULTS[key])==value: return
        if checkpoint: self.view.ws.checkpoint()
        overlay[key]=value; self.recompute(); self.view.ws.dirty()
    def bar_from_position(self,key,x,checkpoint):
        low,high,_,_=BARS[key]; rect=self.control_rects()[key]
        self.set_bar(key,low+(high-low)*min(1.,max(0.,(x-rect.left()-2)/(rect.width()-4))),checkpoint)
    def paint_choice(self,painter,rect,text,vertical,clickable):
        """Draw a title, with chevrons when it opens a choice menu."""
        painter.save(); metrics=QFontMetricsF(painter.font())
        if vertical: painter.translate(rect.center().x(),rect.center().y()); painter.rotate(-90); area=QRectF(-rect.height()/2,-rect.width()/2,rect.height(),rect.width())
        else: area=QRectF(rect)
        text=metrics.elidedText(text,Qt.TextElideMode.ElideRight,max(1.,area.width()-26)); painter.drawText(area,Qt.AlignmentFlag.AlignCenter,text)
        if clickable and not self.exporting: draw_choice_icon(painter,QPointF(area.center().x()-metrics.horizontalAdvance(text)/2-9,area.center().y()))
        painter.restore()
    def paintEvent(self,event):
        ws=self.view.ws; overlay=self.view.overlay; dark=ws.dark; light=not dark; fg=QColor('#eeeeee' if dark else '#202020')
        painter=QPainter(self); painter.setFont(self.font()); painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.fillRect(self.rect(),QColor(DARK_WORKSHEET_BACKGROUND if dark else LIGHT_WORKSHEET_BACKGROUND)); painter.setPen(fg)
        rect=self.plot_rect()
        if not overlay: painter.end(); return
        targets=self.switch_targets(); positions={key:self.switch_pos.get(key,target) for key,target in targets.items()}
        title_font=QFont(self.font())
        if title_font.pointSizeF()>0: title_font.setPointSizeF(title_font.pointSizeF()+2)
        else: title_font.setPixelSize(max(1,title_font.pixelSize())+2)
        if not self.exporting: self.paint_controls(painter,positions,light)
        painter.setFont(title_font); self.paint_choice(painter,self.title_rect(rect),ws.population_name(overlay.get('population')),False,True)
        painter.setFont(self.font())
        if self.data:
            kind,bounds,layers,missing=self.data; (a,b),(c,d)=bounds; stacked=False
            painter.save(); painter.setClipRect(rect)
            if kind=='scatter':
                for image in layers: painter.drawImage(rect,image)
            elif kind=='contour':
                for color,levels,(rows,cols) in layers:
                    color=QColor(color); color.setAlphaF(min(1.,self.bar_value('opacity')/0.6)); painter.setPen(QPen(color,1.))
                    for segments in levels:
                        xs=rect.left()+(segments[:,[0,2]]+.5)/cols*rect.width(); ys=rect.top()+(segments[:,[1,3]]+.5)/rows*rect.height()
                        painter.drawLines([QLineF(x1,y1,x2,y2) for (x1,x2),(y1,y2) in zip(xs.tolist(),ys.tolist())])
            else:
                # Lanes share one height scale; later samples are drawn in front, like a ridge plot once offset.
                offset,lane,base_of=self.lane_layout(rect,len(layers)); stacked=offset>=0.15
                for i,(color,edges,counts,name) in enumerate(layers):
                    base=base_of(i); color=QColor(color); fill=QColor(color); fill.setAlpha(round(75*self.bar_value('opacity')/0.6))
                    points=QPolygonF([QPointF(rect.left(),base)]+[QPointF(rect.left()+(float(edges[j]+edges[j+1])/2-a)/(b-a)*rect.width(),base-(float(v)-c)/(d-c)*lane) for j,v in enumerate(counts)]+[QPointF(rect.right(),base)])
                    painter.setPen(QPen(color,1.6)); painter.setBrush(fill); painter.drawPolygon(points)
            if self.drag_start is not None and self.drag_end is not None:
                zoom=QRectF(self.drag_start,self.drag_end).normalized()
                if kind=='histogram': zoom=QRectF(zoom.left(),rect.top(),zoom.width(),rect.height())
                painter.setPen(QPen(QColor('#287af4'),1.5,Qt.PenStyle.DashLine)); painter.setBrush(QColor(40,122,244,35)); painter.drawRect(zoom)
            painter.restore(); painter.setPen(QPen(fg,1)); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawRect(rect)
            x=overlay['x']; y=overlay.get('y') if kind!='histogram' else None; offset_lanes=kind=='histogram' and overlay.get('offset',0.)>0
            xf=lambda value:rect.left()+(value-a)/(b-a)*rect.width(); yf=lambda value:rect.bottom()-(value-c)/(d-c)*rect.height()
            painter.save(); painter.setFont(tick_font(self.font())); metrics=QFontMetricsF(painter.font())
            xticks,xminor=axis_ticks((a,b),log_scale(x)); yticks,yminor=axis_ticks((c,d),bool(y) and log_scale(y))
            for pos in xminor: painter.drawLine(QPointF(xf(pos),rect.bottom()),QPointF(xf(pos),rect.bottom()+2))
            for pos in ([] if offset_lanes else yminor): painter.drawLine(QPointF(rect.left()-2,yf(pos)),QPointF(rect.left(),yf(pos)))
            for pos,_ in xticks: painter.drawLine(QPointF(xf(pos),rect.bottom()),QPointF(xf(pos),rect.bottom()+4))
            for left,width,label in positioned_tick_labels(xticks,xf,metrics,self.width(),log_scale(x)):
                painter.drawText(QRectF(left,rect.bottom()+5,width,16),Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter,label)
            last=float('inf')
            for pos,value in ([] if offset_lanes else yticks):
                yy=yf(pos); painter.drawLine(QPointF(rect.left()-4,yy),QPointF(rect.left(),yy))
                if last-yy>=metrics.height()+2:
                    painter.drawText(QRectF(rect.left()-52,yy-8,45,16),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,log_tick_label(value) if y and log_scale(y) else tick_label(value)); last=yy
            for i,(color,_,_,name) in enumerate(layers if stacked else []):
                base=base_of(i); painter.setPen(QColor(color)); painter.drawLine(QPointF(rect.left()-4,base),QPointF(rect.left(),base))
                painter.drawText(QRectF(rect.right()-5-rect.width()*0.5,base-metrics.height()-2,rect.width()*0.5,metrics.height()),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,metrics.elidedText(name,Qt.TextElideMode.ElideMiddle,rect.width()*0.5))
            painter.setPen(fg); painter.restore()
            painter.setFont(title_font); self.paint_choice(painter,self.x_title_rect(rect),ws.axis_label(x),False,True)
            if y: self.paint_choice(painter,self.y_title_rect(rect),ws.axis_label(y),True,True)
            else: self.paint_choice(painter,self.y_title_rect(rect),'% of max' if overlay.get('scale')=='modal' else 'Count',True,False)
            painter.setFont(self.font())
            if not stacked: self.paint_legend(painter,rect,fg)
            if missing:
                painter.setPen(QColor('#e88080' if dark else '#a32222')); painter.drawText(QRectF(rect.left()+6,rect.bottom()-40,rect.width()-12,36),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignBottom|Qt.TextFlag.TextWordWrap,'Unavailable: '+', '.join(missing))
        if not overlay['entries']:
            painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,'Drop samples here to add them')
        painter.end()
        if self.drop_hint: paint_drop_cue(self,self.rect().adjusted(4,4,-4,-4),'Add to overlay',dark)
    def paint_legend(self,painter,rect,fg):
        """Draw a figure legend so exported plots identify every visible sample."""
        ws=self.view.ws; names={sample.path:sample.name for sample in ws.samples}
        entries=[e for e in self.view.overlay['entries'] if e.get('visible',True)]
        if not entries: return
        metrics=QFontMetricsF(painter.font()); line=metrics.height()+3
        labels=[metrics.elidedText(names.get(e['path'],Path(e['path']).name),Qt.TextElideMode.ElideMiddle,max(40.,rect.width()*0.45)) for e in entries]
        width=max(metrics.horizontalAdvance(label) for label in labels)+30; box=QRectF(rect.right()-width-8,rect.top()+8,width,line*len(labels)+8)
        background=QColor(DARK_WORKSHEET_BACKGROUND if ws.dark else LIGHT_WORKSHEET_BACKGROUND); background.setAlpha(210)
        painter.save(); painter.setClipRect(rect); painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(background); painter.drawRoundedRect(box,4,4)
        for i,(entry,label) in enumerate(zip(entries,labels)):
            top=box.top()+4+i*line; painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(entry['color'])); painter.drawRoundedRect(QRectF(box.left()+8,top+line/2-5,10,10),2,2)
            painter.setPen(fg); painter.drawText(QRectF(box.left()+24,top,width-26,line),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,label)
        painter.restore()
    def hit(self,pos):
        """Name the interactive element at a position, if any."""
        if not self.view.overlay: return None
        rect=self.plot_rect()
        for key,area in self.control_rects().items():
            if area.contains(pos): return key
        if self.title_rect(rect).contains(pos): return 'population'
        if self.x_title_rect(rect).contains(pos): return 'x'
        if self.scatter() and self.y_title_rect(rect).contains(pos): return 'y'
        if rect.contains(pos) and self.data: return 'plot'
        return None
    def toggle(self,key):
        self.switch_pos.update({k:v for k,v in self.switch_targets().items() if k not in self.switch_pos}); overlay=self.view.overlay
        if key=='kind': self.view.kind.setCurrentIndex(1-self.view.kind.currentIndex())
        elif key=='style': self.view.set_option('style','density' if overlay.get('style')=='contour' else 'contour')
        else: self.view.set_option('scale','count' if overlay.get('scale')=='modal' else 'modal')
        self.switch_timer.start()
    def mousePressEvent(self,e):
        if e.button()!=Qt.MouseButton.LeftButton: return
        target=self.hit(e.position()); rect=self.plot_rect(); dark=self.view.ws.dark
        if target in ('kind','scale','style'): self.toggle(target)
        elif target in BARS: self.bar_drag=target; self.bar_from_position(target,e.position().x(),True)
        elif target=='population': choice_menu(self,self.view.population,self.title_rect(rect).bottomLeft(),dark)
        elif target=='x': choice_menu(self,self.view.x,self.x_title_rect(rect).topLeft(),dark)
        elif target=='y': choice_menu(self,self.view.y,QPointF(rect.left(),rect.center().y()),dark)
        elif target=='plot': self.drag_start=e.position(); self.drag_end=None
    def mouseMoveEvent(self,e):
        if self.bar_drag: self.bar_from_position(self.bar_drag,e.position().x(),False); return
        if self.drag_start is not None:
            rect=self.plot_rect(); pos=e.position(); self.drag_end=QPointF(min(max(pos.x(),rect.left()),rect.right()),min(max(pos.y(),rect.top()),rect.bottom())); self.update(); return
        target=self.hit(e.position())
        tips={'kind':'Switch between overlaid histograms and scatter plots','scale':'Raw counts, or each sample scaled to its own highest peak','style':'Density layers or equal-probability contours',
              'offset':'Separate overlaid histograms into offset lanes','opacity':'Opacity of fills, density layers and contour lines','levels':'Number of contour lines; the outermost encloses 95% of events','population':'Choose the population shown for every sample','x':'Choose the X channel','y':'Choose the Y channel',
              'plot':'Drag to zoom · double-click to go back'}
        if target in ('plot',None): self.unsetCursor()
        else: self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tips.get(target,''))
    def mouseReleaseEvent(self,e):
        if self.bar_drag: self.bar_drag=None; return
        if self.drag_start is None: return
        start,end=self.drag_start,self.drag_end; self.drag_start=self.drag_end=None
        if end is not None: self.zoom_to(QRectF(start,end).normalized())
        self.update()
    def mouseDoubleClickEvent(self,e):
        if self.hit(e.position())=='plot': self.drag_start=self.drag_end=None; self.view.set_zoom(self.zoom_stack.pop() if self.zoom_stack else None)
    def zoom_to(self,area):
        """Zoom to a widget rectangle; histograms zoom only along X."""
        if not self.data: return
        kind,((a,b),(c,d)),_,_=self.data; rect=self.plot_rect()
        if area.width()<5 or (kind!='histogram' and area.height()<5): return
        tx=lambda px:a+(px-rect.left())/rect.width()*(b-a); ty=lambda py:c+(rect.bottom()-py)/rect.height()*(d-c)
        xs=[tx(area.left()),tx(area.right())]; self.zoom_stack.append(self.view.overlay.get('zoom'))
        self.view.set_zoom([xs,[ty(area.bottom()),ty(area.top())] if kind!='histogram' else None])
    def contextMenuEvent(self,event):
        menu=QMenu(self); menu.addAction('Copy plot',self.view.copy_plot); menu.addAction('Export plot PNG',self.view.export_plot); menu.addAction('Copy statistics',self.view.copy_statistics)
        if self.view.overlay and self.view.overlay.get('zoom'): menu.addSeparator(); menu.addAction('Reset zoom',lambda:self.view.set_zoom(None))
        menu.exec(event.globalPos())
    def export_image(self):
        """Grab the plot without interactive switches or choice markers."""
        self.exporting=True
        try: return self.grab()
        finally: self.exporting=False; self.update()


class OverlayView(QWidget):
    def __init__(self,ws):
        super().__init__(); self.ws=ws; self.overlay_id=None; self.loading=False; self.setAcceptDrops(True)
        layout=QVBoxLayout(self); layout.setContentsMargins(14,4,14,10); layout.setSpacing(8)
        # Hidden combos hold the choices; the plot's titles and switches drive them.
        self.kind=QComboBox(self); self.kind.addItem('Histogram','histogram'); self.kind.addItem('Scatter','scatter')
        self.x=QComboBox(self); self.y=QComboBox(self); self.population=QComboBox(self)
        for combo in (self.kind,self.x,self.y,self.population): combo.hide()
        self.graph=OverlayGraph(self); layout.addWidget(self.graph,1)
        hint=QLabel('Drag in the plot to zoom · double-click to go back · first listed sample is drawn at the back (top lane when offset) · drag samples to reorder · double-click to open one'); hint.setObjectName('muted'); layout.addWidget(hint)
        self.legend=QListWidget(); self.legend.setDragDropMode(QListWidget.DragDropMode.InternalMove); self.legend.setDefaultDropAction(Qt.DropAction.MoveAction); self.legend.setMaximumHeight(160)
        self.legend.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.legend.customContextMenuRequested.connect(self.legend_menu); layout.addWidget(self.legend)
        actions=QHBoxLayout()
        for text,callback in [('Add samples…',self.add_samples),('Color…',self.choose_color),('Remove sample',self.remove_sample)]:
            button=QPushButton(text); button.clicked.connect(callback); actions.addWidget(button)
        actions.addStretch()
        for text,callback in [('Rename',lambda:self.ws.rename_overlay(self.overlay_id)),('Duplicate',lambda:self.ws.duplicate_overlay(self.overlay_id)),('Delete overlay',lambda:self.ws.remove_overlay(self.overlay_id))]:
            button=QPushButton(text); button.clicked.connect(callback); actions.addWidget(button)
        layout.addLayout(actions)
        for combo in (self.kind,self.x,self.y,self.population): combo.currentIndexChanged.connect(self.changed)
        self.legend.itemChanged.connect(self.visibility_changed); self.legend.model().rowsMoved.connect(self.reorder); self.legend.itemDoubleClicked.connect(lambda item:self.ws.show_sample(item.data(Qt.ItemDataRole.UserRole)))
    @property
    def overlay(self):
        return next((o for o in self.ws.overlays if o['id']==self.overlay_id),None)
    def show_overlay(self,oid):
        self.overlay_id=oid; self.graph.switch_pos={}; self.graph.zoom_stack=[]; self.refresh()
    def refresh(self):
        overlay=self.overlay
        if not overlay: return
        if 'offset' not in overlay: overlay['offset']=round(1-overlay.get('overlap',0.3),2) if overlay.get('layout')=='stacked' else 0.
        overlay.pop('layout',None); overlay.pop('overlap',None)
        self.loading=True; ws=self.ws; paths={e['path'] for e in overlay['entries']}
        names=list(dict.fromkeys(p.name for s in ws.samples if s.path in paths for p in s.parameters)) or list(dict.fromkeys(p.name for s in ws.samples for p in s.parameters))
        for combo,key,fallbacks in ((self.x,'x',('FL1-A','FSC-A')),(self.y,'y',('SSC-A','FSC-H'))):
            combo.clear()
            for name in names: combo.addItem(ws.axis_label(name),name)
            selected=combo.findData(overlay.get(key))
            for fallback in fallbacks:
                if selected<0: selected=combo.findData(fallback)
            combo.setCurrentIndex(max(0,selected)); overlay[key]=combo.currentData() or overlay.get(key,'')
        self.kind.setCurrentIndex(max(0,self.kind.findData(overlay.get('kind','histogram'))))
        self.population.clear(); self.population.addItem('All Events',None)
        for gate in ws.main_gates: self.population.addItem(ws.population_name(gate.id),gate.id)
        self.population.setCurrentIndex(max(0,self.population.findData(overlay.get('population'))))
        overlay.pop('normalized',None)
        self.legend.clear(); by_path={s.path:s for s in ws.samples}
        for entry in overlay['entries']:
            sample=by_path.get(entry['path'])
            if sample:
                stats=ws.stats_cache.get(sample,ws.gates_for(sample),overlay.get('population'),overlay['x'])
                count='—' if stats['count'] is None else f"{stats['count']:,} events"; median='' if stats['median'] is None else f" · median {tick_label(stats['median'])}"
                text=f'{sample.name}    {count}{median}'
            else: text=Path(entry['path']).name+' (missing)'
            item=QListWidgetItem(text); item.setToolTip(entry['path'])
            item.setData(Qt.ItemDataRole.UserRole,entry['path']); item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable|Qt.ItemFlag.ItemIsDragEnabled)
            item.setCheckState(Qt.CheckState.Checked if entry.get('visible',True) else Qt.CheckState.Unchecked)
            item.setIcon(swatch(entry['color'])); self.legend.addItem(item)
        self.loading=False; self.graph.recompute()
    def changed(self,*args):
        overlay=self.overlay
        if self.loading or not overlay: return
        values=dict(kind=self.kind.currentData(),x=self.x.currentData(),y=self.y.currentData(),population=self.population.currentData())
        if all(overlay.get(key)==value for key,value in values.items()): return
        self.ws.checkpoint()
        if any(overlay.get(key)!=values[key] for key in ('kind','x','y')): overlay['zoom']=None
        overlay.update(values); self.refresh(); self.ws.overlay_changed()
    def set_option(self,key,value):
        overlay=self.overlay
        if not overlay or overlay.get(key)==value: return
        self.ws.checkpoint(); overlay[key]=value; self.refresh(); self.ws.dirty()
    def set_zoom(self,zoom):
        overlay=self.overlay
        if not overlay or overlay.get('zoom')==zoom: return
        self.ws.checkpoint(); overlay['zoom']=zoom; self.graph.recompute(); self.ws.dirty()
    def visibility_changed(self,item):
        overlay=self.overlay
        if self.loading or not overlay: return
        entry=next((e for e in overlay['entries'] if e['path']==item.data(Qt.ItemDataRole.UserRole)),None)
        if entry and entry.get('visible',True)!=(item.checkState()==Qt.CheckState.Checked):
            self.ws.checkpoint(); entry['visible']=item.checkState()==Qt.CheckState.Checked; self.graph.recompute(); self.ws.dirty()
    def reorder(self,*args):
        overlay=self.overlay
        if self.loading or not overlay: return
        entries={e['path']:e for e in overlay['entries']}; order=[self.legend.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.legend.count())]
        if order!=[e['path'] for e in overlay['entries']] and sorted(order)==sorted(entries):
            self.ws.checkpoint(); overlay['entries']=[entries[path] for path in order]; self.graph.recompute(); self.ws.dirty()
    def selected_entry(self):
        item=self.legend.currentItem(); overlay=self.overlay
        return next((e for e in overlay['entries'] if item and e['path']==item.data(Qt.ItemDataRole.UserRole)),None) if overlay else None
    def choose_color(self):
        entry=self.selected_entry()
        if not entry: return
        color=QColorDialog.getColor(QColor(entry['color']),self,'Sample color')
        if color.isValid() and color.name()!=entry['color']: self.ws.checkpoint(); entry['color']=color.name(); self.refresh(); self.ws.dirty()
    def remove_sample(self):
        entry=self.selected_entry()
        if entry: self.ws.checkpoint(); self.overlay['entries'].remove(entry); self.refresh(); self.ws.overlay_changed()
    def add_samples(self):
        overlay=self.overlay
        if not overlay: return
        present={e['path'] for e in overlay['entries']}; available=[s for s in self.ws.samples if s.path not in present]
        if not available: return
        dialog=SampleChooser(self,'Add samples',available)
        if dialog.exec(): self.ws.add_to_overlay(overlay['id'],dialog.paths())
    def legend_menu(self,pos):
        item=self.legend.itemAt(pos)
        if not item: return
        self.legend.setCurrentItem(item); menu=QMenu(self)
        menu.addAction('Open sample',lambda:self.ws.show_sample(item.data(Qt.ItemDataRole.UserRole))); menu.addAction('Color…',self.choose_color); menu.addAction('Remove from overlay',self.remove_sample)
        menu.exec(self.legend.viewport().mapToGlobal(pos))
    def statistics_rows(self):
        overlay=self.overlay; by_path={s.path:s for s in self.ws.samples}; population=self.ws.population_name(overlay.get('population'))
        rows=[['Sample','Population','Parameter','Events','% of parent','Median','Mean']]
        for entry in overlay['entries']:
            sample=by_path.get(entry['path'])
            if not sample: continue
            stats=self.ws.stats_cache.get(sample,self.ws.gates_for(sample),overlay.get('population'),overlay['x'])
            rows.append([sample.name,population,overlay['x'],stats['count'],stats['percent_parent'],stats['median'],stats['mean']])
        return rows
    def copy_statistics(self):
        if self.overlay: QApplication.clipboard().setText(export_csv(self.statistics_rows(),'\t'))
    def copy_plot(self):
        QApplication.clipboard().setPixmap(self.graph.export_image())
    def export_plot(self):
        path,_=remembered(QFileDialog.getSaveFileName(self,'Export plot',start_folder(),'PNG (*.png)'))
        if path: self.graph.export_image().save(path,'PNG')
    def dragEnterEvent(self,e):
        if dragged_paths(e.mimeData()) and self.overlay: e.acceptProposedAction(); self.graph.drop_hint=True; self.graph.update()
        else: e.ignore()
    def dragMoveEvent(self,e):
        if dragged_paths(e.mimeData()) and self.overlay: e.acceptProposedAction()
        else: e.ignore()
    def dragLeaveEvent(self,e):
        self.graph.drop_hint=False; self.graph.update()
    def dropEvent(self,e):
        self.graph.drop_hint=False; self.graph.update(); paths=dragged_paths(e.mimeData())
        if paths and self.overlay: self.ws.add_to_overlay(self.overlay_id,paths); e.acceptProposedAction()
