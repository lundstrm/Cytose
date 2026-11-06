"""Compensation matrix dialog: control assignments, spillover estimation, manual edits and a live preview."""
from __future__ import annotations
import re
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetricsF, QImage, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)
from .core import compensation_channels, fluor_base, fluorescence_channels, membership, spillover_from_controls, transform
from .dialogs import ChoiceCombo, add_done

PREVIEW_EVENTS = 20000


def stain_choices(samples):
    """Detector bases with their stain labels, e.g. ('FL1', 'FL1 · FITC')."""
    choices={}
    for sample in samples:
        for p in sample.parameters:
            base=fluor_base(p.name)
            if p.name in fluorescence_channels([sample]) and base not in choices:
                label=fluor_base(p.stain) if p.stain and fluor_base(p.stain)!=base else ''
                choices[base]=f'{base} · {label}' if label else base
    return list(choices.items())


def guess_stain(name, choices):
    """Unstained for names like 'unstained'/'blank'; otherwise the detector or stain named in the file name."""
    lower=name.lower()
    if re.search(r'unst|blank|neg', lower): return 'unstained'
    for base,label in choices:
        for word in [base]+label.split(' · ')[1:]:
            if word and re.search(r'(?<![A-Za-z0-9])'+re.escape(word.lower())+r'(?![A-Za-z0-9])',lower): return base
    return None


def fit_combo(box):
    """Wide enough for the longest entry plus the chevron, so labels are never cut off."""
    metrics=QFontMetricsF(box.font()); box.setMinimumWidth(int(max((metrics.horizontalAdvance(box.itemText(i)) for i in range(box.count())),default=40)+48))


class PreviewGrid(QWidget):
    """Every channel pair after compensation (blue) over the uncompensated data (grey), for one
    sample and population. Axes stay fixed while values are edited; events beyond an axis are
    drawn on that edge."""
    def __init__(self,dialog):
        super().__init__(); self.dialog=dialog; self.setMinimumSize(360,360); self.values=None; self.raw=None; self.bounds=None; self.range_key=None
    def recompute(self):
        dialog=self.dialog; sample=dialog.preview_sample(); channels=dialog.channels; self.values=None
        if sample is not None and channels:
            names=[p.name for p in sample.parameters]
            if all(names.count(name)==1 for name in channels):
                population=dialog.population.currentData()
                mask=membership(sample,dialog.ws.gates_for(sample),population) if sample in dialog.ws.samples else np.ones(len(sample.events),dtype=bool)
                raw=sample.events_raw[mask][:,[names.index(name) for name in channels]]
                if len(raw)>PREVIEW_EVENTS: raw=raw[np.random.default_rng(0).choice(len(raw),PREVIEW_EVENTS,replace=False)]
                try: self.values=transform(raw@np.linalg.inv(dialog.matrix()),True)
                except np.linalg.LinAlgError: self.values=None
                self.raw=transform(raw,True); key=(sample.path,population,tuple(channels))
                if key!=self.range_key:
                    # Range from the uncompensated data plus room below zero; kept until the selection changes.
                    self.range_key=key; self.bounds=[]
                    for column in self.raw.T:
                        finite=column[np.isfinite(column)]; lo,hi=(float(np.percentile(finite,.5)),float(np.percentile(finite,99.5))) if len(finite) else (0.,1.)
                        span=max(hi-lo,1.); self.bounds.append((min(lo,0.)-0.15*span,hi+0.05*span))
        self.update()
    def density(self,values,x,y,color):
        (a,b),(c,d)=self.bounds[x],self.bounds[y]
        # Clip to the range so events outside it collect on the plot edges.
        xs=np.clip(values[:,x],a,b); ys=np.clip(values[:,y],c,d); valid=np.isfinite(xs)&np.isfinite(ys)
        counts,_,_=np.histogram2d(xs[valid],ys[valid],bins=48,range=[[a,b],[c,d]]); counts=counts.T[::-1]
        if not counts.max(): return None
        rgba=np.zeros(counts.shape+(4,),dtype=np.uint8); rgba[...,0]=color.red(); rgba[...,1]=color.green(); rgba[...,2]=color.blue()
        rgba[...,3]=np.where(counts>0,(color.alpha()*(0.25+0.75*np.log1p(counts)/np.log1p(counts.max()))),0).astype(np.uint8)
        return QImage(rgba.data,48,48,4*48,QImage.Format.Format_RGBA8888).copy()
    def paintEvent(self,event):
        dark=self.dialog.ws.dark; fg=QColor('#c9c9cc' if dark else '#3a3a37'); painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        channels=self.dialog.channels; n=len(channels)
        if self.values is None or n<2 or not self.bounds:
            painter.setPen(fg); painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'No preview for this selection'); painter.end(); return
        margin=34; cells=n-1; legend=20; side=(min(self.width(),self.height()-legend)-margin)/cells
        accent=QColor('#6fafe7' if dark else '#356b9c'); grey=QColor('#8b8b90' if dark else '#8a897f'); grey.setAlpha(150)
        painter.setFont(self.font())
        for row in range(cells):
            for col in range(row+1):
                y,x=row+1,col; rect=QRectF(margin+col*side+2,legend+row*side+2,side-4,side-4)
                for values,color in ((self.raw,grey),(self.values,accent)):
                    image=self.density(values,x,y,color)
                    if image is not None: painter.drawImage(rect,image)
                (a,b),(c,d)=self.bounds[x],self.bounds[y]; zero=QColor(fg); zero.setAlpha(70); painter.setPen(QPen(zero,1,Qt.PenStyle.DashLine))
                if a<0<b: zx=rect.left()+(0-a)/(b-a)*rect.width(); painter.drawLine(QPointF(zx,rect.top()),QPointF(zx,rect.bottom()))
                if c<0<d: zy=rect.bottom()-(0-c)/(d-c)*rect.height(); painter.drawLine(QPointF(rect.left(),zy),QPointF(rect.right(),zy))
                frame=QColor(fg); frame.setAlpha(110); painter.setPen(QPen(frame,1)); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawRect(rect)
                if col==0:
                    painter.save(); painter.setPen(fg); painter.translate(margin-8,rect.center().y()); painter.rotate(-90)
                    painter.drawText(QRectF(-side/2,-12,side,16),Qt.AlignmentFlag.AlignCenter,channels[y]); painter.restore()
                if row==cells-1: painter.setPen(fg); painter.drawText(QRectF(rect.left(),rect.bottom()+4,rect.width(),16),Qt.AlignmentFlag.AlignCenter,channels[x])
        # Legend: compensated vs uncompensated.
        x=self.width()-8
        for label,color in (('Uncompensated',grey),('Compensated',accent)):
            width=QFontMetricsF(painter.font()).horizontalAdvance(label); x-=width
            painter.setPen(fg); painter.drawText(QRectF(x,0,width,16),Qt.AlignmentFlag.AlignVCenter,label)
            x-=14; painter.setPen(Qt.PenStyle.NoPen); solid=QColor(color); solid.setAlpha(255); painter.setBrush(solid); painter.drawRoundedRect(QRectF(x,4,9,9),2,2); x-=14
        painter.end()


class CompensationDialog(QDialog):
    def __init__(self,ws):
        super().__init__(ws); self.ws=ws; self.setWindowTitle('Compensation'); self.resize(1060,620)
        everything=ws.samples+ws.controls; current=ws.compensation
        self.channels=compensation_channels(everything)
        matrix=np.eye(len(self.channels)); saved=current.get('channels') or []
        if current.get('matrix') and len(current['matrix'])==len(saved):
            index={name:i for i,name in enumerate(saved)}
            for i,a in enumerate(self.channels):
                for j,b in enumerate(self.channels):
                    if a in index and b in index: matrix[i,j]=current['matrix'][index[a]][index[b]]
        outer=QVBoxLayout(self); outer.setContentsMargins(18,16,18,14); outer.setSpacing(8); columns=QHBoxLayout(); columns.setSpacing(24); outer.addLayout(columns,1)
        left=QVBoxLayout(); left.setSpacing(8); columns.addLayout(left,3)
        self.enabled=QCheckBox('Apply compensation'); self.enabled.setChecked(bool(current.get('enabled'))); left.addWidget(self.enabled)
        heading=QHBoxLayout(); caption=QLabel('Controls'); caption.setStyleSheet('font-weight:bold;'); heading.addWidget(caption); heading.addStretch()
        choose=QPushButton('Choose controls…'); choose.setToolTip('Pick which files are compensation controls'); choose.clicked.connect(self.choose_controls); heading.addWidget(choose); left.addSpacing(6); left.addLayout(heading)
        self.controls_area=QWidget(); self.controls_layout=QGridLayout(self.controls_area); self.controls_layout.setContentsMargins(0,0,0,0); self.controls_layout.setHorizontalSpacing(12); self.controls_layout.setVerticalSpacing(4); left.addWidget(self.controls_area)
        self.stain_boxes={}; self.choices=stain_choices(everything)
        actions=QHBoxLayout(); actions.setSpacing(6)
        self.calculate=QPushButton('Calculate from controls'); self.calculate.clicked.connect(self.from_controls)
        reset=QPushButton('Reset'); reset.setToolTip('No spillover (identity matrix)'); reset.clicked.connect(lambda:self.show_matrix(np.eye(len(self.channels))))
        for button in (self.calculate,reset): actions.addWidget(button)
        actions.addStretch(); left.addSpacing(6); left.addLayout(actions)
        note=QLabel('Spillover in % · each row spills into the columns · double-click a value to edit'); note.setObjectName('muted'); left.addWidget(note)
        self.table=QTableWidget(len(self.channels),len(self.channels)); self.table.setHorizontalHeaderLabels(self.channels); self.table.setVerticalHeaderLabels(self.channels)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); left.addWidget(self.table,1)
        right=QVBoxLayout(); right.setSpacing(6); columns.addLayout(right,4)
        pickers=QHBoxLayout(); title=QLabel('Preview'); title.setStyleSheet('font-weight:bold;'); pickers.addWidget(title); pickers.addStretch()
        self.sample=ChoiceCombo(); self.population=ChoiceCombo(); pickers.addWidget(self.sample); pickers.addWidget(self.population); right.addLayout(pickers)
        self.preview=PreviewGrid(self); right.addWidget(self.preview,1)
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(150); self.timer.timeout.connect(self.preview.recompute)
        self.table.itemChanged.connect(lambda item:self.timer.start()); self.sample.currentIndexChanged.connect(lambda i:self.timer.start()); self.population.currentIndexChanged.connect(lambda i:self.timer.start())
        self.population.addItem('All Events',None)
        for gate in ws.main_gates: self.population.addItem(ws.population_name(gate.id),gate.id)
        fit_combo(self.population)
        self.rebuild_controls(); self.show_matrix(matrix); add_done(self,outer,default=False); self.preview.recompute()
    def rebuild_controls(self):
        """Control rows with their stain choices, and the preview's sample list (controls first)."""
        stains=self.stains() if self.stain_boxes else dict(self.ws.control_stains)
        while self.controls_layout.count():
            widget=self.controls_layout.takeAt(0).widget()
            if widget: widget.deleteLater()
        self.stain_boxes={}
        if not self.ws.controls:
            hint=QLabel('No controls yet: use “Choose controls…”.'); hint.setObjectName('muted'); self.controls_layout.addWidget(hint,0,0)
        for row,control in enumerate(self.ws.controls):
            self.controls_layout.addWidget(QLabel(control.name),row,0); box=ChoiceCombo(); box.addItem('Not used',None); box.addItem('Unstained','unstained')
            for base,label in self.choices: box.addItem(label,base)
            box.setCurrentIndex(max(0,box.findData(stains.get(control.path)))); fit_combo(box); self.controls_layout.addWidget(box,row,1); self.stain_boxes[control.path]=box
        self.controls_layout.setColumnStretch(0,1); self.calculate.setEnabled(bool(self.ws.controls))
        previous=self.sample.currentData(); self.sample.blockSignals(True); self.sample.clear()
        for control in self.ws.controls: self.sample.addItem(control.name+' (control)',control.path)
        for sample in self.ws.samples: self.sample.addItem(sample.name,sample.path)
        self.sample.setCurrentIndex(max(0,self.sample.findData(previous))); fit_combo(self.sample); self.sample.blockSignals(False)
    def preview_sample(self):
        path=self.sample.currentData(); return next((s for s in self.ws.controls+self.ws.samples if s.path==path),None)
    def choose_controls(self):
        from .overlay import SampleChooser
        everything=sorted(self.ws.samples+self.ws.controls,key=lambda s:s.name.lower())
        dialog=SampleChooser(self,'Compensation controls',everything,{c.path for c in self.ws.controls})
        if not dialog.exec(): return
        chosen=set(dialog.paths()); current={c.path for c in self.ws.controls}
        if chosen-current: self.ws.move_to_controls(sorted(chosen-current))
        if current-chosen: self.ws.move_to_samples(sorted(current-chosen))
        self.rebuild_controls(); self.timer.start()
    def show_matrix(self,matrix):
        self.table.blockSignals(True); suffix=lambda name:name[len(fluor_base(name)):]
        for i in range(len(self.channels)):
            for j in range(len(self.channels)):
                item=QTableWidgetItem(f'{100*matrix[i,j]:.2f}'); item.setTextAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
                if i==j or suffix(self.channels[i])!=suffix(self.channels[j]): item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i,j,item)
        self.table.blockSignals(False); self.timer.start()
    def matrix(self):
        n=len(self.channels); matrix=np.eye(n)
        for i in range(n):
            for j in range(n):
                try: matrix[i,j]=1. if i==j else float(self.table.item(i,j).text())/100
                except (ValueError,AttributeError): pass
        return matrix
    def stains(self): return {path:box.currentData() for path,box in self.stain_boxes.items() if box.currentData()}
    def from_controls(self):
        stains=self.stains(); controls=[c for c in self.ws.controls if c.path in stains]
        self.show_matrix(spillover_from_controls(controls,stains,self.channels)); self.enabled.setChecked(True)
    def result(self):
        return {'enabled':self.enabled.isChecked(),'channels':self.channels,'matrix':self.matrix().tolist()},self.stains()
