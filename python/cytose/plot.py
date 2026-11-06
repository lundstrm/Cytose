"""Interactive scatter plotting; all event counts are computed in the core."""
from __future__ import annotations
import re
import math
import weakref
from collections import OrderedDict
import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QPolygonF, QTextLayout, QTextOption, QTransform
from PySide6.QtWidgets import QWidget, QMenu
from .core import log_scale, quadrant_mask, membership, population_available, population_signature, transform, inverse
from .histogram import histogram_series

LIGHT_WORKSHEET_BACKGROUND = '#e5e4df'
DARK_WORKSHEET_BACKGROUND = '#1d1d1f'
HISTOGRAM = '__histogram__'


def axis_ticks(bounds, logarithmic):
    lo,hi=bounds
    if not logarithmic:
        return [(lo+(hi-lo)*i/4,float(inverse(lo+(hi-lo)*i/4,False))) for i in range(5)],[]
    major=[]; minor=[]
    for value in [0.]+[sign*10.**exponent for exponent in range(19) for sign in (-1,1)]:
        pos=float(transform(value,True))
        if lo<=pos<=hi: major.append((pos,value))
    for exponent in range(19):
        for multiple in range(2,10):
            for sign in (-1,1):
                pos=float(transform(sign*multiple*10.**exponent,True))
                if lo<pos<hi: minor.append(pos)
    major.sort(); minor.sort()
    if len(major)<2:
        major=[(lo+(hi-lo)*i/4,float(inverse(lo+(hi-lo)*i/4,True))) for i in range(5)]
    return major,minor


def tick_label(value):
    magnitude=abs(value)
    for limit,suffix in ((1e9,'G'),(1e6,'M'),(1e3,'k')):
        if magnitude>=limit: return f'{value/limit:.3g}{suffix}'
    return f'{value:.3g}'


def tick_font(font):
    """Use a slightly smaller version of the same font for tick numbers."""
    result=QFont(font)
    if result.pixelSize()>0: result.setPixelSize(max(1,round(result.pixelSize()*5/6)))
    elif result.pointSizeF()>0: result.setPointSizeF(max(1,result.pointSizeF()*.85))
    return result


def log_tick_label(value):
    if abs(value)>=1000:
        exponent=round(np.log10(abs(value)))
        if np.isclose(abs(value),10.**exponent): return ('-' if value<0 else '')+f'1e{exponent}'
    return tick_label(value)

def positioned_tick_labels(ticks,position,metrics,width,logarithmic):
    """Place labels inside the widget, leaving a visible gap between them."""
    labels=[]; last_right=-float('inf')
    for value_pos,value in ticks:
        label=log_tick_label(value) if logarithmic else tick_label(value)
        text_width=metrics.horizontalAdvance(label)+2
        if text_width>width: continue
        left=max(0.,min(position(value_pos)-text_width/2,width-text_width))
        if left<last_right+3: continue
        labels.append((left,text_width,label)); last_right=left+text_width
    return labels


def draw_choice_icon(painter,center):
    """Small up/down chevrons marking a clickable title that opens a choice menu."""
    x,y=center.x(),center.y()
    painter.drawLine(QPointF(x-3,y-2),QPointF(x,y-5)); painter.drawLine(QPointF(x,y-5),QPointF(x+3,y-2))
    painter.drawLine(QPointF(x-3,y+2),QPointF(x,y+5)); painter.drawLine(QPointF(x,y+5),QPointF(x+3,y+2))


def choice_menu(widget,combo,position,dark):
    """Show a combo box's items as a checkable menu at a widget position and apply the choice."""
    if not combo.count(): return
    menu=QMenu(widget)  # styled by the app stylesheet, like every other menu
    for index in range(combo.count()):
        action=menu.addAction(combo.itemText(index)); action.setData(index); action.setCheckable(True); action.setChecked(index==combo.currentIndex())
    choice=menu.exec(widget.mapToGlobal(position.toPoint()))
    if choice: combo.setCurrentIndex(choice.data())


def title_layout(text,font,width):
    """Wrap at word boundaries, splitting a word only when it cannot fit."""
    layout=QTextLayout(text,font); option=QTextOption(); option.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere); layout.setTextOption(option)
    layout.beginLayout(); height=0.
    while True:
        line=layout.createLine()
        if not line.isValid(): break
        line.setLineWidth(max(1,width)); line.setPosition(QPointF(0,height)); height+=line.height()
    layout.endLayout()
    return layout,height


class ScatterPlot(QWidget):
    changed = Signal()
    opened = Signal(str)
    activated = Signal(object)
    editRequested = Signal(str)
    closeRequested = Signal(object)
    def __init__(self, workspace, population=None, x=None, y=None):
        super().__init__()
        self.workspace, self.population = workspace, population
        self.x, self.y = x, y
        self.bounds = None
        self.zoom_history = []
        self.draft = []
        self.start = None
        self.drag_cursor = None
        self.selected = None
        self.edit_vertex = None
        self.edit_edge = None
        self.quadrant_drag = None
        self.quadrant_drag_ids = ()
        self.label_drag = None
        self.drag_changed = False
        self.cursor = None
        self.hover = None
        self.label_hits = {}
        self.plot_drag_start = None
        self.plot_dragging = False
        self._density_key = None
        self._density_image = None
        self._density_cache = OrderedDict()
        self._axis_label_cache = OrderedDict()
        self._histogram_cache = None
        self.setMinimumSize(320, 340)
        self.setMaximumSize(400, 420)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sample(self):
        return self.workspace.sample()

    def axes(self):
        s = self.sample()
        if not s or not s.parameters or (self.y!=HISTOGRAM and len(s.parameters)<2):
            return None
        names = [p.name for p in s.parameters]
        if self.x not in names: self.x = 'FSC-A' if 'FSC-A' in names else names[0]
        if self.y==HISTOGRAM: return names.index(self.x),names.index(self.x)
        if self.y not in names: self.y = 'SSC-A' if 'SSC-A' in names else names[1]
        return names.index(self.x), names.index(self.y)

    def reset(self):
        s, axes = self.sample(), self.axes()
        if not axes: return
        if self.y==HISTOGRAM:
            edges,series,_=histogram_series([s],self.workspace.gates,self.population,self.x,log_scale(self.x))
            maximum=float(series[0][1].max()) if series else 0.
            self.bounds=[(float(edges[0]),float(edges[-1])),(0.,max(1.,maximum*1.1))]; self.update(); return
        ranges = []
        for col, name in zip(axes, (self.x, self.y)):
            values = transform(s.events[:, col], log_scale(name))
            values = values[np.isfinite(values)]
            lo, hi = (float(values.min()), float(values.max())) if len(values) else (0., 1.)
            ranges.append((lo, hi if hi > lo else lo+1))
        self.bounds = ranges
        self.update()

    def plot_rect(self):
        scale=self.workspace.plot_zoom; top=self.workspace.plot_title_height
        left=max(76*scale,math.ceil(self.y_tick_width()+35*scale))
        n = min(self.width()-left-29*scale, self.height()-top-68*scale)
        return QRectF(left, top, max(1,n), max(1,n))

    def y_tick_width(self):
        if self.bounds is None: return 35.*self.workspace.plot_zoom
        ticks,_=axis_ticks(self.bounds[1],log_scale(self.y or ''))
        metrics=QFontMetricsF(tick_font(self.font()))
        return max((metrics.horizontalAdvance(log_tick_label(value) if log_scale(self.y or '') else tick_label(value)) for _,value in ticks),default=0.)+2*self.workspace.plot_zoom

    def title_text(self):
        names=[]; gate_id=self.population; seen=set()
        while gate_id is not None and gate_id not in seen:
            seen.add(gate_id); gate=next((g for g in self.workspace.gates if g.id==gate_id),None)
            if not gate: break
            names.insert(0,gate.name); gate_id=gate.parent
        return ' › '.join(['All Events']+names)

    def axis_label_rects(self):
        r=self.plot_rect()
        scale=self.workspace.plot_zoom
        # Keep the same gap between the numeric label area and either title.
        return (QRectF(r.left(),r.bottom()+26*scale,r.width(),18*scale),
                QRectF(r.left()-30*scale-self.y_tick_width(),r.top(),18*scale,r.height()))

    def axis_label_image(self,text,color,width,height,vertical=False):
        """Render both titles identically, rotating the finished pixels for Y."""
        ratio=self.devicePixelRatioF(); font=self.font()
        key=(text,font.toString(),color.rgba(),width,height,ratio,vertical)
        image=self._axis_label_cache.pop(key,None)
        if image is None:
            image=QImage(max(1,math.ceil(width*ratio)),max(1,math.ceil(height*ratio)),QImage.Format.Format_ARGB32_Premultiplied)
            image.setDevicePixelRatio(ratio); image.fill(Qt.GlobalColor.transparent)
            painter=QPainter(image); painter.setFont(font); painter.setPen(color); painter.setRenderHint(QPainter.RenderHint.TextAntialiasing,True)
            painter.drawText(QRectF(0,0,width,height),Qt.AlignmentFlag.AlignCenter,text); painter.end()
            if vertical: image=image.transformed(QTransform().rotate(-90),Qt.TransformationMode.FastTransformation)
        self._axis_label_cache[key]=image
        if len(self._axis_label_cache)>8: self._axis_label_cache.popitem(last=False)
        return image

    def move_gate(self,gate,start,end):
        """Translate in display coordinates while retaining finite raw values."""
        transformed=[[float(transform(x,log_scale(self.x))),float(transform(y,log_scale(self.y)))] for x,y in gate.vertices]
        requested=[float(transform(end[0],log_scale(self.x))-transform(start[0],log_scale(self.x))),
                   float(transform(end[1],log_scale(self.y))-transform(start[1],log_scale(self.y)))]
        delta=requested[:]; limit=float(np.log10(np.finfo(float).max))-1e-9
        for axis,name in enumerate((self.x,self.y)):
            if log_scale(name):
                values=[v[axis] for v in transformed]
                delta[axis]=max(-limit-min(values),min(limit-max(values),delta[axis]))
        return [[float(inverse(x+delta[0],log_scale(self.x))),float(inverse(y+delta[1],log_scale(self.y)))] for x,y in transformed]

    ELLIPSE_POINTS=48
    ELLIPSE_HANDLES=(0,12,24,36)
    def ellipse_vertices(self,x0,x1,y0,y1):
        """Sample an axis-aligned ellipse in display coordinates and return raw vertices."""
        cx,cy,rx,ry=(x0+x1)/2,(y0+y1)/2,abs(x1-x0)/2,abs(y1-y0)/2; angles=np.linspace(0,2*np.pi,self.ELLIPSE_POINTS,endpoint=False)
        return [[float(inverse(cx+rx*np.cos(t),log_scale(self.x))),float(inverse(cy+ry*np.sin(t),log_scale(self.y)))] for t in angles]
    ELLIPSE_ROTATE=-1
    def ellipse_frame(self,gate):
        """Centre, unit axes and radii of an ellipse gate in widget pixels."""
        points=[self.xy(*v) for v in gate.vertices]; cx=sum(p.x() for p in points)/len(points); cy=sum(p.y() for p in points)/len(points)
        u=(points[0].x()-cx,points[0].y()-cy); v=(points[12].x()-cx,points[12].y()-cy); rx=math.hypot(*u) or 1.; ry=math.hypot(*v) or 1.
        return (cx,cy),(u[0]/rx,u[1]/rx),rx,(v[0]/ry,v[1]/ry),ry
    def set_ellipse_frame(self,gate,center,u,rx,v,ry):
        angles=np.linspace(0,2*np.pi,self.ELLIPSE_POINTS,endpoint=False)
        gate.vertices=[self.raw(QPointF(center[0]+rx*math.cos(t)*u[0]+ry*math.sin(t)*v[0],center[1]+rx*math.cos(t)*u[1]+ry*math.sin(t)*v[1])) for t in angles]
    def rotate_handle(self,gate,with_side=False):
        """Rotation knob beyond one end of the minor axis, on the side that stays inside the plot."""
        (cx,cy),_,_,v,ry=self.ellipse_frame(gate); extra=18*self.workspace.plot_zoom; r=self.plot_rect()
        for sign in (1,-1):
            knob=QPointF(cx+sign*v[0]*(ry+extra),cy+sign*v[1]*(ry+extra))
            if r.contains(knob): break
        else: sign=1; knob=QPointF(cx+v[0]*(ry+extra),cy+v[1]*(ry+extra))
        return (knob,sign) if with_side else knob
    def ellipse_box(self,gate):
        xs=[float(transform(v[0],log_scale(self.x))) for v in gate.vertices]; ys=[float(transform(v[1],log_scale(self.y))) for v in gate.vertices]
        return min(xs),max(xs),min(ys),max(ys)

    def xy(self, x, y):
        r = self.plot_rect(); (a,b),(c,d) = self.bounds
        return QPointF(r.left()+(float(transform(x,log_scale(self.x)))-a)/(b-a)*r.width(), r.bottom()-(float(transform(y,log_scale(self.y)))-c)/(d-c)*r.height())

    def raw(self, pos):
        r=self.plot_rect(); (a,b),(c,d)=self.bounds
        values=[a+(pos.x()-r.left())/r.width()*(b-a),c+(r.bottom()-pos.y())/r.height()*(d-c)]
        limit=float(np.log10(np.finfo(float).max))-1e-9
        return [float(inverse(np.clip(value,-limit,limit) if log_scale(name) else value,log_scale(name))) for value,name in zip(values,(self.x,self.y))]

    def clamp_point(self, pos):
        r=self.plot_rect()
        return QPointF(max(r.left(),min(r.right(),pos.x())),max(r.top(),min(r.bottom(),pos.y())))

    def near_spoke(self,gate,pos,tolerance=6):
        center,ends=self.spoke_ends(gate)
        for end in ends:
            dx,dy=end.x()-center.x(),end.y()-center.y(); length=dx*dx+dy*dy
            t=max(0,min(1,((pos.x()-center.x())*dx+(pos.y()-center.y())*dy)/length)) if length else 0
            if (QPointF(center.x()+t*dx,center.y()+t*dy)-pos).manhattanLength()<=tolerance: return True
        return False
    def gate_at(self, pos, quadrant_area=False):
        """Gate under the pointer. Quadrants are only hit on their lines, so gates beneath stay
        clickable; quadrant_area also accepts a quadrant's area when no other gate is there."""
        x,y=self.raw(pos); area=None
        for gate in reversed(self.workspace.gates):
            if gate.parent!=self.population or gate.x!=self.x or gate.y!=self.y: continue
            if gate.quadrant is not None:
                if quadrant_mask(gate,[x],[y])[0]:
                    if self.near_spoke(gate,pos): return gate.id,None
                    area=area or gate.id
                continue
            if len(gate.vertices)<3: continue
            points=[self.xy(*v) for v in gate.vertices]
            if gate.shape=='ellipse' and gate.id==self.selected and (self.rotate_handle(gate)-pos).manhattanLength()<10: return gate.id,self.ELLIPSE_ROTATE
            for index,point in enumerate(points):
                if gate.shape=='ellipse' and index not in self.ELLIPSE_HANDLES: continue
                if (point-pos).manhattanLength()<10: return gate.id,index
            if self.rectangle(gate):
                for index,(a,b) in enumerate(zip(points,points[1:]+points[:1])):
                    dx,dy=b.x()-a.x(),b.y()-a.y(); length=dx*dx+dy*dy
                    if length:
                        t=max(0,min(1,((pos.x()-a.x())*dx+(pos.y()-a.y())*dy)/length))
                        if (QPointF(a.x()+t*dx,a.y()+t*dy)-pos).manhattanLength()<7: return gate.id,('edge',index)
            if QPolygonF(points).containsPoint(pos,Qt.FillRule.OddEvenFill): return gate.id,None
        return (area,None) if quadrant_area and area else (None,None)

    def label_shift(self,gate):
        """Pixel offset of a moved label; stored in display-data units so it follows zoom and gate moves."""
        if not gate.label_offset or not self.bounds: return QPointF(0,0)
        r=self.plot_rect(); (a,b),(c,d)=self.bounds
        return QPointF(gate.label_offset[0]/(b-a)*r.width(),-gate.label_offset[1]/(d-c)*r.height())
    def place_label(self,gate,x,y,width,height):
        r=self.plot_rect(); shift=self.label_shift(gate)
        return QRectF(max(r.left(),min(x+shift.x(),r.right()-width)),max(r.top(),min(y+shift.y(),r.bottom()-height)),width,height)
    def spoke_ends(self,gate):
        """Pixel centre and where each spoke (top, right, bottom, left) leaves the plot."""
        tx,ty=gate.quadrant[:2]; center=self.xy(tx,ty); r=self.plot_rect(); ends=[]
        defaults=((0,-1),(1,0),(0,1),(-1,0))
        for index,default in enumerate(defaults):
            if gate.spokes:
                anchor=self.xy(*gate.spokes[index]); d=(anchor.x()-center.x(),anchor.y()-center.y())
                if abs(d[0])<1e-9 and abs(d[1])<1e-9: d=default
            else: d=default
            steps=[t for t in ((r.left()-center.x())/d[0] if d[0]<0 else (r.right()-center.x())/d[0] if d[0]>0 else math.inf,
                               (r.top()-center.y())/d[1] if d[1]<0 else (r.bottom()-center.y())/d[1] if d[1]>0 else math.inf) if t>=0]
            t=min(steps) if steps else 0; ends.append(QPointF(center.x()+d[0]*t,center.y()+d[1]*t))
        return center,ends
    def quadrant_handle_at(self,gate,pos):
        if not gate or gate.quadrant is None: return None
        center,ends=self.spoke_ends(gate)
        if (center-pos).manhattanLength()<=9: return 'both'
        return next((f'spoke{index}' for index,point in enumerate(ends) if (point-pos).manhattanLength()<=9),None)

    def quadrant_siblings(self,gate):
        return [g for g in self.workspace.gates if g.quadrant is not None and g.parent==gate.parent and g.x==gate.x and g.y==gate.y
                and (g.quadrant_group==gate.quadrant_group if gate.quadrant_group else not g.quadrant_group and g.quadrant[:2]==gate.quadrant[:2])]

    @staticmethod
    def rectangle(gate):
        v=gate.vertices
        return len(v)==4 and v[0][1]==v[1][1] and v[1][0]==v[2][0] and v[2][1]==v[3][1] and v[3][0]==v[0][0]

    def density_image(self,s,axes):
        gates=(tuple((g.id,g.parent,g.x,g.y,g.color,tuple(map(tuple,g.vertices)),tuple(g.quadrant or ()),tuple(map(tuple,g.spokes or ()))) for g in self.workspace.gates)
               if self.workspace.backgating else population_signature(self.workspace.gates,self.population))
        key=(id(s),id(s.events),tuple(axes),self.population,self.x,self.y,tuple(map(tuple,self.bounds)),self.workspace.backgating,self.workspace.dark,gates)
        if self.drag_changed and self._density_image is not None: return self._density_image
        entry=self._density_cache.pop(key,None)
        if entry is None or entry[0]() is not s or entry[1]() is not s.events:
            entry=(weakref.ref(s),weakref.ref(s.events),self._make_density(s,axes))
        self._density_cache[key]=entry
        if len(self._density_cache)>8: self._density_cache.popitem(last=False)
        self._density_key=key; self._density_image=entry[2]
        return self._density_image

    def histogram_counts(self,s):
        key=(id(s),id(s.events),population_signature(self.workspace.gates,self.population),self.x,tuple(self.bounds[0]))
        if self._histogram_cache is None or self._histogram_cache[0]!=key:
            self._histogram_cache=(key,histogram_series([s],self.workspace.gates,self.population,self.x,log_scale(self.x),bounds=self.bounds[0]))
        return self._histogram_cache[1]

    def _make_density(self,s,axes):
        mask=membership(s,self.workspace.gates,self.population)
        values=s.events[mask]
        if len(values):
            x=transform(values[:,axes[0]],log_scale(self.x)); y=transform(values[:,axes[1]],log_scale(self.y))
            (a,b),(c,d)=self.bounds
            # Events outside the view are drawn on the nearest edge, so none silently disappear.
            valid=np.isfinite(x)&np.isfinite(y)
            x=np.clip(x[valid],a,b); y=np.clip(y[valid],c,d)
            size=256
            h,_,_=np.histogram2d(x,y,bins=size,range=[[a,b],[c,d]])
            counts=h.T[::-1]; maximum=counts.max(); intensity=np.log(np.maximum(counts,1))/np.log(maximum) if maximum>1 else np.zeros_like(counts)
            if maximum:
                rgba=np.zeros((size,size,4),dtype=np.uint8)
                hue=(0.57 if self.workspace.dark else 0.64)*(1-intensity); sat=0.72 if self.workspace.dark else 0.78
                value=(0.93+0.06*intensity) if self.workspace.dark else (0.78+0.13*intensity)
                sector=hue*6; chroma=value*sat; secondary=chroma*(1-np.abs(sector%2-1)); offset=value-chroma
                rgba[:,:,0]=((offset+np.select([sector<1,sector<2,sector<4,sector<5],[chroma,secondary,0,secondary],default=chroma))*255).astype(np.uint8)
                rgba[:,:,1]=((offset+np.select([sector<1,sector<3,sector<4],[secondary,chroma,secondary],default=0))*255).astype(np.uint8)
                rgba[:,:,2]=((offset+np.select([sector<2,sector<3,sector<5],[0,secondary,chroma],default=secondary))*255).astype(np.uint8)
                rgba[:,:,3]=np.where(counts>0,255,0)
                image=QImage(rgba.data,size,size,4*size,QImage.Format.Format_RGBA8888).copy()
                if self.workspace.backgating:
                    rgba[:,:,0:3]=217 if self.workspace.dark else 0; rgba[:,:,3]=np.where(counts>0,255,0)
                    visible_indices=np.flatnonzero(mask)[valid]
                    for gate in self.workspace.gates:
                        if not gate.color: continue
                        parent=gate.parent; seen=set()
                        while parent is not None and parent != self.population and parent not in seen:
                            seen.add(parent); ancestor=next((g for g in self.workspace.gates if g.id==parent),None); parent=ancestor.parent if ancestor else None
                        if parent != self.population: continue
                        selected=membership(s,self.workspace.gates,gate.id)[visible_indices]
                        gh,_,_=np.histogram2d(x[selected],y[selected],bins=size,range=[[a,b],[c,d]])
                        occupied=gh.T[::-1]>0; color=QColor(gate.color)
                        rgba[occupied]=[color.red(),color.green(),color.blue(),230]
                    image=QImage(rgba.data,size,size,4*size,QImage.Format.Format_RGBA8888).copy()
                return image
        return None

    def paintEvent(self, event):
        p=QPainter(self); p.setFont(self.font()); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark=self.workspace.dark
        fg=QColor('#eeeeee' if dark else '#202020'); bg=QColor(DARK_WORKSHEET_BACKGROUND if dark else LIGHT_WORKSHEET_BACKGROUND)
        p.fillRect(super().rect(),bg); p.setPen(fg)
        title=self.title_text()
        title_rect=self.plot_rect(); layout,height=title_layout(title,self.font(),title_rect.width())
        layout.draw(p,QPointF(title_rect.left(),max(0,(title_rect.top()-height)/2)))
        if self.closable() and self.underMouse():
            scale=self.workspace.plot_zoom; p.setPen(fg); p.drawText(QRectF(self.width()-27*scale,scale,22*scale,22*scale),Qt.AlignmentFlag.AlignCenter,'×')
        p.setPen(fg)
        axes=self.axes(); s=self.sample()
        if not axes: p.end(); return
        if self.bounds is None: self.reset()
        r=self.plot_rect()
        if self.y==HISTOGRAM:
            edges,series,_=self.histogram_counts(s)
            if series:
                counts=series[0][1]; (a,b),(c,d)=self.bounds
                path=QPolygonF([QPointF(r.left(),r.bottom())]+[QPointF(r.left()+(float(edges[i]+edges[i+1])/2-a)/(b-a)*r.width(),r.bottom()-(float(value)-c)/(d-c)*r.height()) for i,value in enumerate(counts)]+[QPointF(r.right(),r.bottom())])
                p.save(); p.setClipRect(r); color=QColor('#6fafe7' if dark else '#356b9c'); fill=QColor(color); fill.setAlpha(55)
                p.setPen(QPen(color,1.2)); p.setBrush(fill); p.drawPolygon(path); p.restore()
        else:
            image=self.density_image(s,axes)
            if image is not None: p.drawImage(r,image)
        if not population_available(s,self.workspace.gates,self.population):
            p.setPen(QColor('#c23537')); p.drawText(r,Qt.AlignmentFlag.AlignCenter,'Gate channel unavailable')
        p.setPen(QPen(fg,1)); p.drawRect(r)
        p.save(); p.setFont(tick_font(self.font()))
        scale=self.workspace.plot_zoom
        xticks,xminor=axis_ticks(self.bounds[0],log_scale(self.x)); yticks,yminor=axis_ticks(self.bounds[1],log_scale(self.y))
        xf=lambda value: r.left()+(value-self.bounds[0][0])/(self.bounds[0][1]-self.bounds[0][0])*r.width()
        yf=lambda value: r.bottom()-(value-self.bounds[1][0])/(self.bounds[1][1]-self.bounds[1][0])*r.height()
        for pos in xminor: p.drawLine(QPointF(xf(pos),r.bottom()),QPointF(xf(pos),r.bottom()+2))
        for pos in yminor: p.drawLine(QPointF(r.left()-2,yf(pos)),QPointF(r.left(),yf(pos)))
        for pos,value in xticks:
            xx=xf(pos); p.drawLine(QPointF(xx,r.bottom()),QPointF(xx,r.bottom()+4*scale))
        for left,width,label in positioned_tick_labels(xticks,xf,QFontMetricsF(p.font()),self.width(),log_scale(self.x)):
            p.drawText(QRectF(left,r.bottom()+5*scale,width,16*scale),Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter,label)
        last_y=float('inf')
        for pos,value in yticks:
            yy=yf(pos); p.drawLine(QPointF(r.left()-4,yy),QPointF(r.left(),yy)); label=log_tick_label(value) if log_scale(self.y) else tick_label(value)
            if last_y-yy>=p.fontMetrics().height()+2:
                p.drawText(QRectF(r.left()-7*scale-self.y_tick_width(),yy-8*scale,self.y_tick_width(),16*scale),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,label); last_y=yy
        p.restore(); p.setFont(self.font()); p.setPen(fg)
        x_label,y_label=self.axis_label_rects()
        x_image=self.axis_label_image(self.workspace.axis_label(self.x),fg,r.width(),x_label.height())
        y_image=self.axis_label_image('Count' if self.y==HISTOGRAM else self.workspace.axis_label(self.y),fg,r.height(),y_label.width(),vertical=True)
        # Draw at native size on device-pixel boundaries: scaling or rotating in
        # the widget painter can otherwise make one title appear lighter.
        ratio=self.devicePixelRatioF()
        for rect,label_image in ((x_label,x_image),(y_label,y_image)):
            width=label_image.width()/ratio; height=label_image.height()/ratio
            origin=QPointF(round((rect.center().x()-width/2)*ratio)/ratio,round((rect.center().y()-height/2)*ratio)/ratio)
            p.drawImage(origin,label_image)
        self.label_hits = {}
        p.save(); p.setClipRect(r)
        for g in self.workspace.gates:
            if g.parent != self.population or g.x != self.x or g.y != self.y: continue
            gate_color=QColor(g.color) if g.color else fg
            if g.quadrant is not None:
                tx,ty,hx,hy=g.quadrant[:4]; pos,ends=self.spoke_ends(g); p.setPen(QPen(gate_color,1))
                for end in ends: p.drawLine(pos,end)
                label_x=max(r.left(),pos.x())+4 if hx else r.left()+4
                label_y=r.top()+4 if hy else max(r.top(),pos.y())+4
                percent=self.workspace.gate_percentages.get(g.id)
                text=g.name+(f'\n{percent:.1f}%' if percent is not None else '')
                metrics=QFontMetricsF(p.font()); lines=text.split('\n')
                label_rect=self.place_label(g,label_x,label_y,max(metrics.horizontalAdvance(line) for line in lines)+4*scale,metrics.lineSpacing()*len(lines)+2*scale); self.label_hits[g.id]=label_rect
                p.drawText(label_rect,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop,text)
                if self.selected==g.id:
                    p.setBrush(gate_color)
                    for handle in [pos]+ends:
                        p.drawEllipse(handle,3*scale,3*scale)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                continue
            if len(g.vertices)<3: continue
            points=QPolygonF([self.xy(*v) for v in g.vertices])
            if not points.boundingRect().intersects(r): continue
            p.setPen(QPen(gate_color,(2 if self.selected == g.id else 1.5)*scale)); p.drawPolygon(points)
            if self.selected == g.id:
                p.setBrush(gate_color)
                for index,vertex in enumerate(points):
                    if g.shape!='ellipse' or index in self.ELLIPSE_HANDLES: p.drawEllipse(vertex,3*scale,3*scale)
                if g.shape=='ellipse':
                    knob,side=self.rotate_handle(g,True); p.setBrush(Qt.BrushStyle.NoBrush); p.drawLine(points[12 if side==1 else 36],knob); p.drawEllipse(knob,4*scale,4*scale)
                p.setBrush(Qt.BrushStyle.NoBrush)
            anchor=points.boundingRect().topLeft()+QPointF(2,-4)
            percent=self.workspace.gate_percentages.get(g.id)
            label=g.name+(f'\n{percent:.1f}%' if percent is not None else '')
            metrics=QFontMetricsF(p.font()); text_width=max(metrics.horizontalAdvance(line) for line in label.split('\n'))+8*scale; text_height=metrics.lineSpacing()*len(label.split('\n'))+3*scale
            text_width=min(text_width,r.width())
            label_rect=self.place_label(g,anchor.x(),anchor.y()-text_height,text_width,text_height); self.label_hits[g.id]=label_rect
            p.drawText(label_rect,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop,label)
        p.restore()
        if self.draft:
            p.setPen(QPen(QColor('#ef6130'),1,Qt.PenStyle.DashLine))
            points=[self.xy(*v) for v in self.draft]
            if self.cursor is not None: points.append(self.cursor)
            p.drawPolyline(QPolygonF(points))
            if self.cursor is not None: p.drawEllipse(self.cursor,3,3)
        if self.start is not None and self.drag_cursor is not None and self.workspace.mode in ('rectangle','zoom','ellipse'):
            p.save(); p.setClipRect(r); p.setPen(QPen(QColor('#287af4' if self.workspace.mode=='zoom' else '#ef6130'),1.5,Qt.PenStyle.DashLine))
            p.setBrush(QColor(40,122,244,35) if self.workspace.mode=='zoom' else QColor(239,97,48,25))
            area=QRectF(self.xy(*self.start),self.drag_cursor).normalized(); p.drawEllipse(area) if self.workspace.mode=='ellipse' else p.drawRect(area); p.restore()
        if self.workspace.mode=='quadrant' and self.hover and r.contains(self.hover):
            p.setPen(QPen(QColor('#ef6130'),1,Qt.PenStyle.DashLine))
            p.drawLine(QPointF(self.hover.x(),r.top()),QPointF(self.hover.x(),r.bottom()))
            p.drawLine(QPointF(r.left(),self.hover.y()),QPointF(r.right(),self.hover.y()))
        p.end()

    def axis_menu(self, pos):
        s=self.sample(); r=self.plot_rect()
        if not s: return False
        x_label,y_label=self.axis_label_rects(); axis='x' if x_label.contains(pos) else 'y' if y_label.contains(pos) else None
        if axis:
            menu=self.make_axis_menu(axis)
            menu.exec(self.mapToGlobal(pos.toPoint())); return True
        return False

    def make_axis_menu(self,axis):
        menu=QMenu(self)
        if axis=='y':
            action=menu.addAction('Histogram (count)'); action.triggered.connect(lambda:self.set_axis('y',HISTOGRAM)); menu.addSeparator()
        for par in self.sample().parameters:
            action=menu.addAction(self.workspace.axis_label(par.name))
            action.triggered.connect(lambda checked=False, a=axis, n=par.name: self.set_axis(a,n))
        return menu

    def on_selected_handle(self,pos):
        """True when a press lands on a handle of the selected gate, even just outside the plot."""
        if self.selected is None or not self.bounds: return False
        gate,index=self.gate_at(pos); return gate==self.selected and index is not None
    def set_axis(self, axis, name):
        if getattr(self,axis)==name: return
        self.workspace.checkpoint()
        setattr(self,axis,name); self.reset(); self.changed.emit()

    def closable(self):
        """Any plot can be closed while another plot remains."""
        return len(self.workspace.plots)>1
    def mousePressEvent(self, e):
        scale=self.workspace.plot_zoom
        if self.closable() and e.position().x()>=self.width()-27*scale and e.position().y()<=25*scale:
            self.closeRequested.emit(self); return
        self.workspace.active=self; self.activated.emit(self); self.setFocus(); self.update()
        handle=self.workspace.mode=='select' and self.on_selected_handle(e.position())
        if e.button()==Qt.MouseButton.LeftButton and e.position().y()<self.workspace.plot_title_height and not handle:
            self.plot_drag_start=e.globalPosition(); self.plot_dragging=False; return
        if e.button()!=Qt.MouseButton.LeftButton: return  # right-clicks only open the context menu
        if not self.axes() or self.axis_menu(e.position()): return
        if not handle and not self.plot_rect().adjusted(-1,-1,1,1).contains(e.position()): return
        point=self.raw(self.clamp_point(e.position())); mode=self.workspace.mode
        if self.y==HISTOGRAM and mode not in ('select','zoom'): return
        if mode=='polygon':
            self.draft.append(point); self.update(); return
        if mode=='quadrant':
            self.workspace.add_quadrants(self,point); return
        if mode=='select':
            label=next((gid for gid,rect in reversed(list(self.label_hits.items())) if rect.contains(e.position())),None)  # topmost label wins
            selected_gate=next((g for g in self.workspace.gates if g.id==self.selected),None)
            on_handle=self.gate_at(e.position())[1] is not None or bool(self.quadrant_handle_at(selected_gate,e.position()))
            if label is not None and not on_handle:  # gate handles take priority over nearby labels
                # Dragging a name moves only its label; a double-click still opens the gate editor.
                gate=next((g for g in self.workspace.gates if g.id==label),None)
                if gate: self.label_drag=(gate,e.position(),list(gate.label_offset or [0.,0.]),False); return
            selected=next((g for g in self.workspace.gates if g.id==self.selected),None)
            self.quadrant_drag=self.quadrant_handle_at(selected,e.position())
            if self.quadrant_drag: self.edit_vertex=None
            else:
                self.selected,self.edit_vertex=self.gate_at(e.position())
                selected=next((g for g in self.workspace.gates if g.id==self.selected),None)
                self.quadrant_drag=self.quadrant_handle_at(selected,e.position())
            self.quadrant_drag_ids=tuple(g.id for g in self.quadrant_siblings(selected)) if self.quadrant_drag else ()
            self.edit_edge=None
            if isinstance(self.edit_vertex,tuple): self.edit_edge=self.edit_vertex[1]; self.edit_vertex=None
            if self.edit_vertex==self.ELLIPSE_ROTATE: self.rotate_side=self.rotate_handle(next(g for g in self.workspace.gates if g.id==self.selected),True)[1]
            self.drag_changed=False
            self.workspace.selected_gate=self.selected
        self.start=point; self.drag_cursor=self.clamp_point(e.position()); self.update()

    def mouseMoveEvent(self,e):
        if self.plot_drag_start is not None:
            if (e.globalPosition()-self.plot_drag_start).manhattanLength()>=8:
                if not self.plot_dragging: self.workspace.begin_plot_preview(self,self.plot_drag_start)
                self.plot_dragging=True; self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.workspace.update_plot_preview(self,e.globalPosition().toPoint())
            return
        if self.label_drag:
            gate,origin,offset,moved=self.label_drag; delta=e.position()-origin
            if not moved and delta.manhattanLength()<3: return
            if not moved: self.workspace.checkpoint(); gate=next((g for g in self.workspace.gates if g.id==gate.id),gate)
            r=self.plot_rect(); (a,b),(c,d)=self.bounds
            gate.label_offset=[offset[0]+delta.x()/r.width()*(b-a),offset[1]-delta.y()/r.height()*(d-c)]
            self.label_drag=(gate,origin,offset,True); self.update(); return
        if self.workspace.mode=='select' and e.buttons()==Qt.MouseButton.NoButton:
            if any(rect.contains(e.position()) for rect in self.label_hits.values()): self.setCursor(Qt.CursorShape.OpenHandCursor)
            else: self.unsetCursor()
        if self.workspace.mode=='quadrant': self.hover=e.position(); self.update()
        if self.workspace.mode=='polygon' and self.draft:
            self.cursor=self.clamp_point(e.position()); self.update()
        if self.start is None or not self.bounds: return
        if self.workspace.mode in ('zoom','rectangle','ellipse') and not e.buttons()&Qt.MouseButton.LeftButton:
            self.start=None; self.drag_cursor=None; self.update(); return  # the release went elsewhere: cancel the outline
        moving_gate=self.workspace.mode=='select' and self.selected is not None
        self.drag_cursor=e.position() if moving_gate else self.clamp_point(e.position()); point=self.raw(self.drag_cursor)
        if self.workspace.mode=='select' and self.selected:
            g=next((g for g in self.workspace.gates if g.id==self.selected),None)
            if g and g.quadrant is not None and self.quadrant_drag:
                if not self.drag_changed: self.workspace.checkpoint(); self.drag_changed=True
                point=self.raw(self.clamp_point(e.position()))
                # The centre moves the whole set (spokes keep their tilt); an outer handle moves only its spoke.
                center,ends=self.spoke_ends(g)
                if self.quadrant_drag=='both':
                    target=self.clamp_point(e.position()); shift=target-center
                    spokes=[self.raw(end+shift) for end in ends] if g.spokes else None
                else: spokes=[self.raw(end) for end in ends]; spokes[int(self.quadrant_drag[5:])]=point
                for sibling in self.workspace.gates:
                    if sibling.id in self.quadrant_drag_ids:
                        if self.quadrant_drag=='both': sibling.quadrant[0],sibling.quadrant[1]=point
                        sibling.spokes=[list(anchor) for anchor in spokes] if spokes else None
                self.start=point; self.update()
            elif g and g.quadrant is None:
                if not self.drag_changed:
                    self.workspace.checkpoint(); self.drag_changed=True
                if self.edit_edge is not None and self.rectangle(g):
                    i=self.edit_edge; j=(i+1)%4
                    if g.vertices[i][0]==g.vertices[j][0]: g.vertices[i][0]=point[0]; g.vertices[j][0]=point[0]
                    else: g.vertices[i][1]=point[1]; g.vertices[j][1]=point[1]
                elif self.edit_vertex is not None and self.rectangle(g):
                    i=self.edit_vertex; old=g.vertices[i][:]
                    for j in ((i-1)%4,(i+1)%4):
                        if g.vertices[j][0]==old[0]: g.vertices[j][0]=point[0]
                        if g.vertices[j][1]==old[1]: g.vertices[j][1]=point[1]
                    g.vertices[i]=point
                elif self.edit_vertex is not None and g.shape=='ellipse':
                    # Side handles move their own side along the (rotated) axis; the rotate handle turns the ellipse.
                    (cx,cy),u,rx,v,ry=self.ellipse_frame(g); pos=self.drag_cursor; dx,dy=pos.x()-cx,pos.y()-cy
                    if self.edit_vertex==self.ELLIPSE_ROTATE:
                        side=getattr(self,'rotate_side',1); target=math.atan2(dy,dx)-math.atan2(side*v[1],side*v[0]); c,s=math.cos(target),math.sin(target)
                        turn=lambda w:(w[0]*c-w[1]*s,w[0]*s+w[1]*c); self.set_ellipse_frame(g,(cx,cy),turn(u),rx,turn(v),ry)
                    else:
                        side=self.ELLIPSE_HANDLES.index(self.edit_vertex); axis=u if side in (0,2) else v; sign=1 if side in (0,1) else -1
                        radius=rx if side in (0,2) else ry; far=(cx-sign*radius*axis[0],cy-sign*radius*axis[1])
                        reach=sign*((pos.x()-far[0])*axis[0]+(pos.y()-far[1])*axis[1])
                        if reach>4:
                            radius=reach/2; center=(far[0]+sign*radius*axis[0],far[1]+sign*radius*axis[1])
                            self.set_ellipse_frame(g,center,u,radius if side in (0,2) else rx,v,radius if side in (1,3) else ry)
                elif self.edit_vertex is not None:
                    g.vertices[self.edit_vertex]=point
                else:
                    g.vertices=self.move_gate(g,self.start,point)
                self.start=point; self.update()
        elif self.workspace.mode in ('zoom','rectangle','ellipse'): self.update()

    def mouseReleaseEvent(self,e):
        if self.label_drag:
            moved=self.label_drag[3]; self.label_drag=None
            if moved: self.workspace.dirty(); self.changed.emit()
            return
        if self.plot_drag_start is not None:
            if self.plot_dragging:
                self.workspace.move_plot(self,e.globalPosition().toPoint()); self.workspace.end_plot_preview()
            self.plot_drag_start=None; self.plot_dragging=False; self.unsetCursor(); return
        if self.start is None or not self.bounds: return
        end=self.raw(self.clamp_point(e.position())); start=self.start; self.start=None; self.drag_cursor=None
        self.quadrant_drag=None; self.quadrant_drag_ids=()
        if self.workspace.mode=='rectangle' and start != end:
            x0,x1=sorted((start[0],end[0])); y0,y1=sorted((start[1],end[1]))
            if x0<x1 and y0<y1: self.workspace.add_gate(self,[[x0,y0],[x1,y0],[x1,y1],[x0,y1]])
        elif self.workspace.mode=='ellipse' and start != end:
            x0,x1=sorted((float(transform(start[0],log_scale(self.x))),float(transform(end[0],log_scale(self.x)))))
            y0,y1=sorted((float(transform(start[1],log_scale(self.y))),float(transform(end[1],log_scale(self.y)))))
            if x1-x0>1e-9 and y1-y0>1e-9: self.workspace.add_gate(self,self.ellipse_vertices(x0,x1,y0,y1),'ellipse')
        elif self.workspace.mode=='zoom':
            x0,x1=sorted((float(transform(start[0],log_scale(self.x))),float(transform(end[0],log_scale(self.x)))))
            y0,y1=sorted((float(transform(start[1],log_scale(self.y))),float(transform(end[1],log_scale(self.y)))))
            # Clamp to the current view: the pixel round trip can otherwise overshoot by a rounding error.
            (a,b),(c,d)=self.bounds; x0,x1,y0,y1=max(x0,a),min(x1,b),max(y0,c),min(y1,d)
            if x1-x0>1e-8 and y1-y0>1e-8: self.workspace.checkpoint(); self.zoom_history.append(self.bounds); self.bounds=[(x0,x1),(y0,y1)]; self.changed.emit()
        if self.drag_changed:
            self.drag_changed=False; self.workspace.refresh()
        self.update()

    def leaveEvent(self,event):
        self.hover=None; self.cursor=None; self.update(); super().leaveEvent(event)

    def enterEvent(self,event):
        self.update(); super().enterEvent(event)

    def mouseDoubleClickEvent(self,e):
        if self.workspace.mode=='zoom' and self.plot_rect().contains(e.position()):
            # Step back one zoom level, or to the full view when there is no history.
            self.workspace.checkpoint()
            if self.zoom_history: self.bounds=self.zoom_history.pop()
            else: self.reset()
            self.changed.emit(); return
        if self.workspace.mode=='polygon':
            points=self.draft[:]
            last=self.raw(self.clamp_point(e.position()))
            if not points or (self.xy(*points[-1])-self.xy(*last)).manhattanLength()>3: points.append(last)
            if len(points)>=3: self.workspace.add_gate(self,points)
            self.draft=[]; self.cursor=None; self.update(); return
        if self.workspace.mode=='select':
            for gate_id, rect in self.label_hits.items():
                if rect.contains(e.position()): self.editRequested.emit(gate_id); return
            gate_id,_=self.gate_at(e.position(),True) if self.plot_rect().contains(e.position()) else (None,None)
            if gate_id: self.selected=gate_id; self.opened.emit(gate_id)

    def keyPressEvent(self,e):
        if e.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace) and self.selected:
            self.workspace.delete_gate(self.selected); self.selected=None
        elif e.key()==Qt.Key.Key_Escape:
            self.draft=[]; self.update()
        else: super().keyPressEvent(e)

    def contextMenuEvent(self, event):
        menu=QMenu(self)
        menu.addAction('Reset zoom', lambda: (self.workspace.checkpoint(), self.reset(), self.changed.emit()))
        menu.addAction('Copy plot to clipboard', lambda: self.workspace.copy_plot(self))
        menu.addSeparator(); menu.addAction('Duplicate plot',lambda:self.workspace.duplicate_plot(self)); menu.addAction('New All Events plot',self.workspace.add_all_events_plot)
        if self.closable():
            menu.addAction('Close plot', lambda: self.closeRequested.emit(self))
        menu.exec(event.globalPos())
