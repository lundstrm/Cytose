"""Cross-platform Cytose desktop application."""
from __future__ import annotations
import json
import math
import sys
import copy
import time
import weakref
import re
import uuid
import datetime
from dataclasses import asdict
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QTimer, QRectF, QEvent, QPoint, QPointF, QByteArray, QSize
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QFontMetricsF, QIcon, QPainter, QPainterPath, QPen, QPolygonF, QKeySequence, QShortcut, QPageSize, QPdfWriter
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSplitter, QStackedWidget, QStyledItemDelegate, QStyle, QStyleOptionViewItem, QTableWidget, QTableWidgetItem, QTabBar, QTabWidget, QToolButton, QToolTip, QSizePolicy, QVBoxLayout, QWidget, QColorDialog, QCheckBox, QButtonGroup)
from .core import Gate, StatisticsCache, compensate, condition_name, default_gate_name, export_csv, membership, natural_key, population_signature, read_fcs, save_json, statistics
from .plot import DARK_WORKSHEET_BACKGROUND, LIGHT_WORKSHEET_BACKGROUND, HISTOGRAM, ScatterPlot, choice_menu, draw_choice_icon, tick_font, tick_label, title_layout
from .dialogs import ChoiceCombo, add_done, ask_name, new_project_name, remembered, start_folder
from .overlay import OverlayList, OverlayView, SampleChooser, add_entries, dragged_paths, new_overlay, paint_drop_cue, sample_mime, SAMPLE_MIME

STYLE = '''
QWidget { background:#1d1d1f; color:#ebebed; font-family:"Comfortaa"; font-size:12px; }
QMainWindow#mainWindow { background:#151517; }
QLabel#panelTitle { color:#f1f1f2; font-weight:bold; font-size:13px; }
QLabel#muted { color:#a7a7aa; font-size:10px; }
QPushButton, QComboBox, QLineEdit { background:#303032; border:1px solid #38383b; border-radius:5px; padding:5px 9px; }
QPushButton:hover, QComboBox:hover { background:#404044; }
QPushButton:checked { background:#203d61; border-color:#285a90; }
QPushButton#accent { background:#287af4; color:white; border:0; font-weight:bold; }
QPushButton#accent:hover { background:#438cf6; }
QListWidget, QTableWidget { background:#1d1d1f; border:0; gridline-color:#373739; }
QListWidget::item { padding:6px 5px; border-bottom:1px solid #353537; }
QListWidget::item:selected { background:#215ed5; color:white; }
QListWidget::indicator { width:14px; height:14px; border:1px solid #737379; border-radius:3px; background:#29292c; }
QListWidget::indicator:checked { background:#287af4; border-color:#287af4; }
QScrollBar:vertical { background:transparent; width:10px; margin:2px; }
QScrollBar:horizontal { background:transparent; height:10px; margin:2px; }
QScrollBar::handle:vertical { background:#67676c; min-height:28px; border-radius:3px; }
QScrollBar::handle:horizontal { background:#67676c; min-width:28px; border-radius:3px; }
QScrollBar::handle:hover { background:#8b8b90; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; border:0; background:transparent; }
QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }
QHeaderView::section { background:#262628; color:#ddd; border:0; padding:5px; }
QTabWidget::pane { border:0; }
QTabWidget#projectTabs, QTabBar#projectTabBar, QWidget#tabCorner { background:#151517; }
QTabWidget#projectTabs::right-corner { top:-3px; }
QTabBar::tab { background:#262628; color:#c9c9cc; padding:7px 18px; margin:3px 3px 3px 0; border:1px solid transparent; border-radius:5px; }
QTabBar::tab:selected { background:#203d61; color:#fff; border:1px solid #287af4; }
QTabBar::tab:hover:!selected { background:#343438; }
QMenu { background:#29292c; color:#ebebed; border:1px solid #48484d; border-radius:7px; padding:5px; }
QMenu::item { padding:7px 22px 7px 24px; border-radius:4px; background:transparent; }
QMenu::item:selected { background:#365c82; color:white; }
QMenu::item:disabled { color:#77777b; }
QMenu::separator { height:1px; background:#48484d; margin:5px 8px; }
QMenu::indicator { width:14px; height:14px; left:6px; }
QSplitter::handle { background:#1d1d1f; }
QWidget#workspacePage, QSplitter#workspaceSplitter, QSplitter#workspaceSplitter::handle { background:#151517; }
QWidget#panelTile { background:#1d1d1f; border:1px solid #323235; border-radius:8px; }
QPushButton#worksheetAction { background:#303032; border:1px solid #424246; border-radius:6px; padding:0 10px; }
QPushButton#worksheetAction:hover { background:#414145; border-color:#606066; }
QPushButton#worksheetAction:disabled { color:#77777b; background:#272729; border-color:#343437; }
QPushButton#worksheetAction::menu-indicator { width:12px; }
QWidget#toolbarDivider { background:#48484c; }
QPushButton#dialogDone { background:#303032; border:1px solid #424246; border-radius:6px; padding:0 16px; }
QPushButton#dialogDone:hover { background:#414145; border-color:#606066; }
QComboBox::drop-down { border:0; background:transparent; width:24px; }
QComboBox::down-arrow { image:none; width:0; height:0; }
QComboBox QAbstractItemView { background:#29292c; color:#ebebed; border:1px solid #48484d; border-radius:7px; padding:5px; outline:0; }
QComboBox QAbstractItemView::item { padding:7px 12px; min-height:20px; border-radius:4px; }
QComboBox QAbstractItemView::item:selected { background:#365c82; color:white; }
QPushButton#mutedPlus { background:transparent; border:0; color:#a7a7aa; font-size:18px; padding:0 0 3px 0; }
QPushButton#mutedPlus:hover { color:#f1f1f2; background:#303032; border-radius:5px; }
QListWidget#plainList::item { border:0; border-radius:5px; padding:5px 2px; }
'''

TOOLBAR_HEIGHT = 40
LOW_EVENTS = 10000
WARNING_COLOR = '#ef8a30'
UNIQUE_COLOR = '#4ba3f0'

_LIGHT_COLORS={'#1d1d1f':'#e5e4df','#ebebed':'#292929','#f1f1f2':'#202020','#a7a7aa':'#676762','#303032':'#d7d6d0','#38383b':'#c5c4bd','#404044':'#c7c6bf','#203d61':'#c8dbf3','#285a90':'#8eb0df','#287af4':'#286ac9','#438cf6':'#3a7bda','#373739':'#c9c8c1','#353537':'#c9c8c1','#215ed5':'#346dcc','#737379':'#94948d','#29292c':'#efeee9','#67676c':'#aaa9a1','#8b8b90':'#85857e','#262628':'#dcdad4','#ddd':'#30302e','#151517':'#d1d0ca','#c9c9cc':'#4e4e4a','#fff':'#202020','#343438':'#c7c6c0','#42556b':'#b4cae8','#323235':'#c3c1ba','#424246':'#b5b4ad','#414145':'#c4c3bc','#606066':'#9b9a93','#77777b':'#85857e','#272729':'#deddd7','#343437':'#cecdc7','#48484c':'#b5b4ad','#48484d':'#bcbab3','#365c82':'#3a7bda'}
LIGHT_STYLE=re.sub(r'#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}',lambda m:_LIGHT_COLORS.get(m.group().lower(),m.group()),STYLE)

def is_dark(widget):
    current=widget
    while current is not None:
        if hasattr(current,'dark'): return current.dark
        if hasattr(current,'tabs') and current.tabs.currentWidget() is not None: return current.tabs.currentWidget().dark
        current=current.parentWidget()
    return True

class TabIconButton(QPushButton):
    """Small, platform-independent controls for closing and adding tabs."""
    def __init__(self,kind):
        super().__init__(); self.kind=kind
        size=22 if kind=='close' else 28; self.setFixedSize(size,size)
        self.setToolTip('Close tab' if kind=='close' else 'New tab (⌘T / Ctrl+T)')
        self.setAccessibleName('Close tab' if kind=='close' else 'New tab')
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark=is_dark(self)
        if self.kind=='close':
            bar=self.parentWidget()
            hovered=isinstance(bar,QTabBar) and any(bar.tabButton(i,QTabBar.ButtonPosition.RightSide) is self and bar.tabRect(i).contains(bar.mapFromGlobal(self.cursor().pos())) for i in range(bar.count()))
            if not hovered and not self.underMouse(): return
        p.setOpacity(.7 if not self.underMouse() else .9)
        if self.kind=='add':
            p.setPen(QPen(QColor(('#454549' if self.underMouse() else '#323235') if dark else '#b7b6af'),1)); p.setBrush(QColor(('#38383b' if self.underMouse() else '#1d1d1f') if dark else '#e5e4df')); p.drawRoundedRect(QRectF(.5,.5,self.width()-1,self.height()-1),6,6)
        elif self.underMouse():
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#475363')); p.drawRoundedRect(QRectF(1,1,self.width()-2,self.height()-2),5,5)
        p.setPen(QPen(QColor('#e5e5e8' if dark else '#383834'),1.6,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        if self.kind=='close':
            c=self.width()/2; p.drawLine(QPointF(c-4,c-4),QPointF(c+4,c+4)); p.drawLine(QPointF(c+4,c-4),QPointF(c-4,c+4))
        else:
            center=self.width()/2; p.drawLine(QPointF(center-6,center),QPointF(center+6,center)); p.drawLine(QPointF(center,center-6),QPointF(center,center+6))
    def enterEvent(self,event):
        self.update(); super().enterEvent(event)
    def leaveEvent(self,event):
        self.update(); super().leaveEvent(event)


class WorkspaceTabBar(QTabBar):
    def __init__(self):
        super().__init__(); self.setObjectName('projectTabBar'); self.setExpanding(False); self.setMovable(True); self.setUsesScrollButtons(True); self.setMouseTracking(True)
        self.spinner_angle=0; self.spinner_started=time.monotonic(); self.spinner_timer=QTimer(self); self.spinner_timer.setInterval(16); self.spinner_timer.setTimerType(Qt.TimerType.PreciseTimer); self.spinner_timer.timeout.connect(self.advance_spinner)
    def set_save_status(self,index,status):
        self.setTabData(index,status)
        self.setTabToolTip(index,{'unsaved':'Quick analysis has not been saved','saving':'Changes are waiting to be saved or are being saved','saved':'Project saved','error':'Project could not be saved'}.get(status,''))
        if any(self.tabData(i)=='saving' for i in range(self.count())):
            if not self.spinner_timer.isActive(): self.spinner_started=time.monotonic(); self.spinner_timer.start()
        else: self.spinner_timer.stop()
        self.update()
    def advance_spinner(self):
        if not any(self.tabData(i)=='saving' for i in range(self.count())): self.spinner_timer.stop(); return
        self.spinner_angle=int((time.monotonic()-self.spinner_started)*300)%360; self.update()
    def update_close_buttons(self):
        for index in range(self.count()):
            button=self.tabButton(index,QTabBar.ButtonPosition.RightSide)
            if button: button.update()
    def mouseMoveEvent(self,event):
        super().mouseMoveEvent(event); self.update_close_buttons(); self.update()
    def leaveEvent(self,event):
        super().leaveEvent(event); self.update_close_buttons(); self.update()
    def tabSizeHint(self,index):
        return QSize(max(131,self.fontMetrics().horizontalAdvance(self.tabText(index))+74),36)
    def tabInserted(self,index):
        super().tabInserted(index)
        button=TabIconButton('close')
        button.clicked.connect(lambda: self.close_button_clicked(button))
        self.setTabButton(index,QTabBar.ButtonPosition.RightSide,button)
        QTimer.singleShot(0,self.position_add_button)
    def tabLayoutChange(self):
        super().tabLayoutChange(); QTimer.singleShot(0,self.position_add_button)
    def resizeEvent(self,event):
        super().resizeEvent(event); self.position_add_button()
    def pill_rect(self,index):
        """The rounded tab shape; close and new-tab buttons are aligned to it."""
        return QRectF(self.tabRect(index)).adjusted(7,7,-3,-.5)
    def position_add_button(self):
        # Qt centres tab buttons on the whole tab; centre them on the drawn pill instead.
        for index in range(self.count()):
            close=self.tabButton(index,QTabBar.ButtonPosition.RightSide)
            if close:
                pill=self.pill_rect(index); close.move(round(pill.right()-close.width()-4),round(pill.center().y()-close.height()/2))
        button=getattr(self,'add_button',None)
        if button is None: return
        pill=self.pill_rect(self.count()-1) if self.count() else QRectF(0,7,0,28.5)
        right=pill.right()+6 if self.count() else 7
        button.move(round(max(0,min(right,self.width()-button.width()-2))),round(pill.center().y()-button.height()/2)); button.raise_()
    def close_button_clicked(self,button):
        for index in range(self.count()):
            if self.tabButton(index,QTabBar.ButtonPosition.RightSide) is button:
                self.tabCloseRequested.emit(index); return
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setFont(self.font())
        dark=is_dark(self)
        for index in range(self.count()):
            rect=self.pill_rect(index)
            selected=index==self.currentIndex(); hovered=rect.contains(self.mapFromGlobal(self.cursor().pos()))
            p.setPen(QPen(QColor('#287af4' if selected else ('#323235' if dark else '#bcbab3')),1)); p.setBrush(QColor(('#203d61' if selected else '#303032' if hovered else '#1d1d1f') if dark else ('#c8dbf3' if selected else '#d6d5cf' if hovered else '#e5e4df'))); p.drawRoundedRect(rect,6,6)
            status=self.tabData(index); center=QPointF(rect.left()+16,rect.center().y())
            p.save(); p.setOpacity(.68)
            if status in ('saved','error'):
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#54c98a' if status=='saved' else '#f08080')); p.drawEllipse(center,3.5,3.5)
            elif status=='saving':
                p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor('#a8ccff'),1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap)); p.drawArc(QRectF(center.x()-5,center.y()-5,10,10),self.spinner_angle*16,260*16)
            p.restore()
            p.setPen(QColor(('#ffffff' if selected else '#c9c9cc') if dark else '#292929'))
            text_rect=rect.adjusted(30,0,-30,0)
            text=p.fontMetrics().elidedText(self.tabText(index),Qt.TextElideMode.ElideRight,max(0,int(text_rect.width())))
            p.drawText(text_rect,Qt.AlignmentFlag.AlignCenter,text)


class ToolButton(QPushButton):
    """Compact painted icons avoid platform-specific font or icon dependencies."""
    def __init__(self,mode,number,tooltip,checkable=True,shortcut_text=None):
        super().__init__(); self.mode=mode; self.number=number; shortcut_text=shortcut_text or str(number)
        self.setFixedSize(TOOLBAR_HEIGHT,TOOLBAR_HEIGHT); self.setCheckable(checkable); self.setToolTip(f'{tooltip} ({shortcut_text})'); self.setAccessibleName(f'{tooltip}, shortcut {shortcut_text}')
    def paintEvent(self,event):
        p=QPainter(self); p.setFont(self.font()); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled(): p.setOpacity(0.3)
        selected=self.isChecked(); hovering=self.underMouse(); dark=is_dark(self)
        p.setPen(QPen(QColor('#408cff' if selected else ('#505054' if hovering else '#38383b') if dark else ('#aaa9a2' if hovering else '#c0bfb8')),1))
        p.setBrush(QColor(('#203d61' if selected else '#38383b' if hovering else '#2b2b2e') if dark else ('#c8dbf3' if selected else '#c9c8c2' if hovering else '#d7d6d0'))); p.drawRoundedRect(QRectF(.5,.5,self.width()-1,self.height()-1),6,6)
        hint=QFont(self.font()); hint.setPixelSize(9); p.setFont(hint); p.setPen(QColor(('#afcfff' if selected else '#a3a3a8') if dark else ('#365f91' if selected else '#66665f'))); p.drawText(QRectF(24,2,14,11),Qt.AlignmentFlag.AlignCenter,str(self.number))
        icon_color=QColor('#f2f3f5' if dark else '#30302d'); p.setPen(QPen(icon_color,1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin)); p.setBrush(Qt.BrushStyle.NoBrush)
        if self.mode=='select':
            path=QPainterPath(); path.moveTo(13,11); path.lineTo(13,28); path.lineTo(17,24); path.lineTo(20,31); path.lineTo(23,29.5); path.lineTo(20,22.5); path.lineTo(26,22); path.closeSubpath()
            p.setBrush(icon_color); p.setPen(Qt.PenStyle.NoPen); p.drawPath(path)
        elif self.mode=='zoom':
            p.drawEllipse(QRectF(11,11,15,15)); p.drawLine(QPointF(24,24),QPointF(30,30))
        elif self.mode=='rectangle':
            p.setPen(QPen(icon_color,1.6,Qt.PenStyle.DotLine,Qt.PenCapStyle.RoundCap)); p.drawRect(QRectF(10,13,20,17))
        elif self.mode=='ellipse':
            p.setPen(QPen(icon_color,1.6,Qt.PenStyle.DotLine,Qt.PenCapStyle.RoundCap)); p.drawEllipse(QRectF(8,14,24,15))
        elif self.mode=='polygon':
            p.setPen(QPen(icon_color,1.6,Qt.PenStyle.DotLine,Qt.PenCapStyle.RoundCap)); p.drawPolygon(QPolygonF([QPointF(10,18),QPointF(18,11),QPointF(29,16),QPointF(27,28),QPointF(15,31),QPointF(9,25)]))
        elif self.mode=='quadrant':
            p.setPen(QPen(icon_color,1.6,Qt.PenStyle.DotLine,Qt.PenCapStyle.RoundCap)); p.drawLine(QPointF(20,11),QPointF(20,31)); p.drawLine(QPointF(10,21),QPointF(30,21))
        elif self.mode=='reset':
            for x,y,dx,dy in ((11,13,1,1),(29,13,-1,1),(11,29,1,-1),(29,29,-1,-1)):
                p.drawLine(QPointF(x,y),QPointF(x+5*dx,y)); p.drawLine(QPointF(x,y),QPointF(x,y+5*dy))
        elif self.mode=='backgate':
            p.drawEllipse(QRectF(11,12,18,18)); p.setBrush(icon_color); p.drawEllipse(QPointF(20,21),3.5,3.5)
        elif self.mode in ('smaller','bigger'):
            side=10 if self.mode=='smaller' else 18; p.drawRoundedRect(QRectF(20-side/2,21-side/2,side,side),2,2)
        elif self.mode in ('undo','redo'):
            if self.mode=='redo': p.translate(40,0); p.scale(-1,1)
            path=QPainterPath(); path.moveTo(13,17); path.lineTo(22,17); path.arcTo(QRectF(16,17,12,12),90,-180); path.lineTo(17,29); p.drawPath(path)
            p.drawLine(QPointF(13,17),QPointF(16.5,13.5)); p.drawLine(QPointF(13,17),QPointF(16.5,20.5))
        elif self.mode=='annotate':
            path=QPainterPath(); path.moveTo(11,15); path.lineTo(22,15); path.lineTo(29,21.5); path.lineTo(22,28); path.lineTo(11,28); path.closeSubpath(); p.drawPath(path); p.drawEllipse(QPointF(15,21.5),1.3,1.3)
        elif self.mode=='unlock':
            p.drawRoundedRect(QRectF(12,19,16,12),2,2); path=QPainterPath(); path.moveTo(15,19); path.lineTo(15,15); path.arcTo(QRectF(15,10,10,10),180,-180); path.lineTo(25,14); p.drawPath(path)
        elif self.mode=='group':
            for x,y in ((15,16),(25,16),(20,25)): p.drawEllipse(QPointF(x,y),3.6,3.6)
        elif self.mode=='all':
            p.setBrush(icon_color); p.setPen(Qt.PenStyle.NoPen)
            for i in range(3):
                for j in range(3): p.drawEllipse(QPointF(13+i*7,14+j*7),2.2,2.2)
        elif self.mode=='matrix':
            text=QFont(self.font()); text.setPixelSize(13); text.setBold(True); p.setFont(text); p.drawText(QRectF(10,10,20,22),Qt.AlignmentFlag.AlignCenter,'M')
            for x,flip in ((10,1),(30,-1)): p.drawLine(QPointF(x,12),QPointF(x,30)); p.drawLine(QPointF(x,12),QPointF(x+3*flip,12)); p.drawLine(QPointF(x,30),QPointF(x+3*flip,30))
        elif self.mode=='options':
            p.setBrush(icon_color); p.setPen(Qt.PenStyle.NoPen)
            for x in (13,20,27): p.drawEllipse(QPointF(x,21),1.9,1.9)
        elif self.mode=='theme':
            p.drawEllipse(QRectF(11,12,18,18)); path=QPainterPath(); path.moveTo(20,12); path.arcTo(QRectF(11,12,18,18),90,180); path.closeSubpath(); p.setBrush(icon_color); p.drawPath(path)


class ExportButton(QPushButton):
    """Muted header action with a small icon ('export' tray or 'copy' clipboard) and label."""
    def __init__(self,kind='export',text='Export',tooltip='Export the analysis values as CSV or to the clipboard'):
        super().__init__(); self.kind=kind; self.label=text; self.setFixedHeight(26); self.setMinimumWidth(QFontMetricsF(self.font()).horizontalAdvance(text)+38); self.setCursor(Qt.CursorShape.PointingHandCursor); self.setToolTip(tooltip)
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); dark=is_dark(self); hover=self.underMouse()
        if hover: p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#303032' if dark else '#d7d6d0')); p.drawRoundedRect(QRectF(self.rect()),5,5)
        color=QColor(('#f1f1f2' if hover else '#a7a7aa') if dark else ('#202020' if hover else '#676762')); p.setPen(QPen(color,1.4,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin)); p.setBrush(Qt.BrushStyle.NoBrush)
        y=self.height()/2
        if self.kind=='copy':
            p.drawRoundedRect(QRectF(10,y-5,9,11),2,2); p.drawLine(QPointF(8,y+3),QPointF(8,y-6)); p.drawLine(QPointF(8,y-6),QPointF(15,y-6))
        else:
            path=QPainterPath(); path.moveTo(8,y); path.lineTo(8,y+5); path.lineTo(20,y+5); path.lineTo(20,y); p.drawPath(path)
            p.drawLine(QPointF(14,y+2),QPointF(14,y-7)); p.drawLine(QPointF(14,y-7),QPointF(11,y-4)); p.drawLine(QPointF(14,y-7),QPointF(17,y-4))
        p.setFont(self.font()); p.drawText(QRectF(26,0,self.width()-30,self.height()),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,self.label)
    def enterEvent(self,event): self.update(); super().enterEvent(event)
    def leaveEvent(self,event): self.update(); super().leaveEvent(event)


class ColorSwatch(QPushButton):
    """Round color choice; None draws the 'default' swatch and '+' the custom picker."""
    def __init__(self,color,kind='color'):
        super().__init__(); self.color=color; self.kind=kind; self.setCheckable(True); self.setFixedSize(26,26); self.setCursor(Qt.CursorShape.PointingHandCursor)
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); dark=is_dark(self); fg=QColor('#ebebed' if dark else '#292929')
        circle=QRectF(4,4,18,18)
        if self.isChecked() or self.underMouse():
            ring=QColor('#ebebed' if dark else '#292929'); ring.setAlpha(255 if self.isChecked() else 90); p.setPen(QPen(ring,1.5)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawEllipse(QRectF(1,1,24,24))
        if self.kind=='default':
            p.setPen(QPen(QColor('#8b8b90'),1.4)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawEllipse(circle); p.drawLine(QPointF(7.5,18.5),QPointF(18.5,7.5))
        elif self.kind=='custom' and not self.color:
            p.setPen(QPen(QColor('#8b8b90'),1.4,Qt.PenStyle.DashLine)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawEllipse(circle)
            p.setPen(QPen(fg,1.4)); p.drawLine(QPointF(13,9),QPointF(13,17)); p.drawLine(QPointF(9,13),QPointF(17,13))
        else:
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(self.color)); p.drawEllipse(circle)
            if self.kind=='custom':
                # Keep the picker recognisable once it holds a color.
                mark=QColor('#ffffff' if QColor(self.color).lightnessF()<0.6 else '#202020'); p.setPen(QPen(mark,1.6)); p.drawLine(QPointF(13,9.5),QPointF(13,16.5)); p.drawLine(QPointF(9.5,13),QPointF(16.5,13))


class GateDialog(QDialog):
    """Name and color for a gate, in one compact column."""
    PALETTE=('#c23537','#0385ae','#058f60','#a15989','#9f6d55','#ef6130')
    def __init__(self,parent,name,color):
        super().__init__(parent); self.setWindowTitle('Edit gate'); self.color=color
        layout=QVBoxLayout(self); layout.setContentsMargins(18,16,18,14); layout.setSpacing(6)
        layout.addWidget(QLabel('Name')); self.name=QLineEdit(name); self.name.selectAll(); layout.addWidget(self.name); layout.addSpacing(8)
        caption=QLabel('Color'); caption.setObjectName('muted'); layout.addWidget(caption)
        row=QHBoxLayout(); row.setSpacing(4); self.swatches=QButtonGroup(self)
        self.default=ColorSwatch(None,'default'); self.default.setToolTip('Default: worksheet color, no backgating highlight')
        custom_color=color if color and color not in self.PALETTE else None
        self.custom=ColorSwatch(custom_color,'custom'); self.custom.setToolTip('Custom color…')
        for swatch in [self.default]+[ColorSwatch(value) for value in self.PALETTE]+[self.custom]:
            self.swatches.addButton(swatch); row.addWidget(swatch)
            if (color and swatch.color==color and swatch.kind!='default') or (swatch is self.default and not color): swatch.setChecked(True)
        row.addStretch(); layout.addLayout(row)
        self.swatches.buttonClicked.connect(self.choose); layout.addSpacing(10)
        add_done(self,layout); self.setMinimumWidth(320)
    def choose(self,swatch):
        if swatch is self.custom:
            chosen=QColorDialog.getColor(QColor(self.custom.color or self.color or '#c23537'),self,'Gate color')
            if not chosen.isValid():
                previous=next((s for s in self.swatches.buttons() if s is not self.custom and s.color==self.color and (s.kind!='default' or not self.color)),self.default); previous.setChecked(True); return
            self.custom.color=chosen.name(); self.custom.update()
        self.color=swatch.color


class WelcomeChoice(QPushButton):
    def __init__(self,title,description):
        super().__init__(); self.title=title; self.description=description; self.setMinimumSize(190,145); self.setToolTip(description)
    def paintEvent(self,event):
        p=QPainter(self); p.setFont(self.font()); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark=is_dark(self); p.setPen(QPen(QColor('#526a8a' if dark else '#abb6c1'),1)); p.setBrush(QColor(('#303c4e' if self.underMouse() else '#262c35') if dark else ('#d1dce8' if self.underMouse() else '#e0e3e3'))); p.drawRoundedRect(QRectF(1,1,self.width()-2,self.height()-2),9,9)
        p.setPen(QColor('#f1f1f2' if dark else '#292929')); bold=QFont(self.font()); bold.setBold(True); p.setFont(bold); p.drawText(QRectF(15,18,self.width()-30,28),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,self.title)
        p.setFont(self.font()); p.setPen(QColor('#c2c6cc' if dark else '#60615e')); p.drawText(QRectF(15,55,self.width()-30,self.height()-65),Qt.AlignmentFlag.AlignLeft|Qt.TextFlag.TextWordWrap,self.description)


class Comparison(QWidget):
    def __init__(self, workspace):
        super().__init__(); self.ws=workspace; self.setMinimumHeight(200); self.setMouseTracking(True); self.drag_group=None; self.drag_pos=None; self.drag_origin=None; self.drag_bar=None; self.export_light=False
        self.switch_position=1.; self.switch_start=1.; self.switch_target=1.; self.switch_time=0
        self.switch_timer=QTimer(self); self.switch_timer.setInterval(16); self.switch_timer.timeout.connect(self.animate_switch)
        self.preview_order=None; self.positions={}; self.animation_from={}; self.animation_to={}; self.animation_start=0
        self.animation_timer=QTimer(self); self.animation_timer.setInterval(16); self.animation_timer.setTimerType(Qt.TimerType.PreciseTimer); self.animation_timer.timeout.connect(self.advance_animation)
    def groups(self,rows=None):
        present=list(dict.fromkeys(r[1] for r in (self.ws.comparison_rows() if rows is None else rows)))
        return [name for name in self.ws.condition_order if name in present]+[name for name in present if name not in self.ws.condition_order]
    def value_limits(self,rows,groups):
        limits=[row[2] for row in rows if row[2] is not None]
        for group in groups:
            vals=[row[2] for row in rows if row[1]==group and row[2] is not None]
            if len(vals)>1:
                mean=float(np.mean(vals)); sd=float(np.std(vals,ddof=1)); limits.extend((mean-sd,mean+sd))
        return limits
    def plot_geometry(self,groups,limits):
        lo=min(0,min(limits,default=0)); hi=max(0,max(limits,default=0)); span=hi-lo or 1
        metrics=QFontMetricsF(tick_font(self.font()))
        left=max(78,math.ceil(max(metrics.horizontalAdvance(tick_label(lo+span*i/4)) for i in range(5)))+48)
        width=max(1,self.width()-left-12); step=width/max(1,len(groups))
        rotated=any(metrics.horizontalAdvance(group)>step-6 for group in groups)
        longest=max((metrics.horizontalAdvance(group) for group in groups),default=0)
        label_height=min(max(18,math.ceil(longest)+2 if rotated else metrics.height()),max(18,self.height()-220))
        bottom=math.ceil(label_height+58)
        return QRectF(left,54,width,max(1,self.height()-54-bottom)),rotated,label_height
    def title_rect(self,plot_rect=None):
        if plot_rect is None:
            rows=self.ws.comparison_rows(); groups=self.groups(rows); plot_rect,_,_=self.plot_geometry(groups,self.value_limits(rows,groups))
        return QRectF(plot_rect.left(),2,plot_rect.width(),42)
    def switch_rect(self,plot_rect):
        return QRectF(5,plot_rect.center().y()-37,30,74)
    def axis_title_rect(self,plot_rect):
        top=self.switch_rect(plot_rect).bottom()+8
        return QRectF(4,top,32,max(1,self.height()-top-4))
    def animate_switch(self):
        progress=min(1.,(time.monotonic()-self.switch_time)/.18)
        self.switch_position=self.switch_start+(self.switch_target-self.switch_start)*(1-(1-progress)**3)
        if progress>=1: self.switch_timer.stop()
        self.update()
    def draw_choice_icon(self,painter,center): draw_choice_icon(painter,center)
    def open_choice(self,combo,position): choice_menu(self,combo,position,self.ws.dark)
    def bar_rect(self,center,step,y,mean):
        return QRectF(center-step*.29,min(y(0),y(mean)),step*.58,abs(y(0)-y(mean)))
    def drag_preview_rect(self):
        if self.drag_bar is None or self.drag_pos is None or self.drag_origin is None: return None
        return self.drag_bar.translated(self.drag_pos-self.drag_origin)
    def animate_order(self,order):
        targets={group:float(index) for index,group in enumerate(order)}
        if targets==self.animation_to: return
        self.animation_from={group:self.positions.get(group,target) for group,target in targets.items()}
        self.animation_to=targets; self.animation_start=time.monotonic(); self.animation_timer.start()
    def advance_animation(self):
        progress=min(1.,(time.monotonic()-self.animation_start)/.18); eased=1-(1-progress)**3
        self.positions={group:start+(self.animation_to[group]-start)*eased for group,start in self.animation_from.items()}
        if progress>=1:
            self.animation_timer.stop()
            if self.drag_group is None: self.positions={}; self.animation_to={}
        self.update()
    def order_for_position(self,groups,rect,x):
        target=max(0,min(len(groups)-1,int((x-rect.left())/rect.width()*len(groups))))
        order=[group for group in groups if group!=self.drag_group]; order.insert(target,self.drag_group); return order
    def paintEvent(self,event):
        light=self.export_light or not self.ws.dark
        p=QPainter(self); p.setFont(self.font()); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.fillRect(self.rect(),QColor('#ffffff' if self.export_light else LIGHT_WORKSHEET_BACKGROUND if light else '#1d1d1f'))
        foreground=QColor('#292929' if light else '#dddddd'); dots=QColor('#454545' if light else '#dedede')
        rows=self.ws.comparison_rows(); groups=self.groups(rows); values=[r[2] for r in rows if r[2] is not None]
        limits=self.value_limits(rows,groups)
        r,rotated,label_height=self.plot_geometry(groups,limits)
        title=self.ws.pop.currentText() or 'All Events'; title_rect=self.title_rect(r)
        title_font=QFont(self.font())
        if title_font.pointSizeF()>0: title_font.setPointSizeF(title_font.pointSizeF()+2)
        else: title_font.setPixelSize(max(1,title_font.pixelSize())+2)
        p.setFont(title_font); p.setPen(foreground); text=p.fontMetrics().elidedText(title,Qt.TextElideMode.ElideRight,max(1,int(title_rect.width()-26)))
        title_line=QRectF(title_rect.left(),title_rect.top(),title_rect.width(),24)
        p.drawText(title_line,Qt.AlignmentFlag.AlignCenter,text)
        if not self.export_light:
            x=title_line.center().x()-p.fontMetrics().horizontalAdvance(text)/2-9
            self.draw_choice_icon(p,QPointF(x,title_line.center().y()))
        p.setFont(self.font())
        if not self.export_light:
            switch=self.switch_rect(r); half=switch.height()/2
            p.setPen(QPen(QColor('#b0afa8' if light else '#414145'),1)); p.setBrush(QColor('#d4d3cd' if light else '#252528')); p.drawRoundedRect(switch,6,6)
            selected=QRectF(switch.left()+2,switch.top()+2+self.switch_position*half,switch.width()-4,half-4)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#365c82')); p.drawRoundedRect(selected,4,4)
            p.setPen(QColor('#eeeeee')); p.setFont(title_font)
            for index,label in enumerate(('%','Mean' if self.ws.metric_combo.currentText()=='Mean' else 'MFI')):
                active=(index==0)==(self.ws.metric_combo.currentText()=='% of parent')
                p.setPen(QColor('#eeeeee' if active else '#70706a' if light else '#858589'))
                p.save(); p.translate(switch.center().x(),switch.top()+(index+.5)*half); p.rotate(-90)
                p.drawText(QRectF(-half/2,-switch.width()/2,half,switch.width()),Qt.AlignmentFlag.AlignCenter,label); p.restore()
            p.setFont(self.font())
            p.save(); p.setFont(title_font)
            upper_width=p.fontMetrics().horizontalAdvance('of parent')
            p.translate(switch.center().x(),switch.top()-8-upper_width/2); p.rotate(-90)
            p.setPen(foreground if self.ws.metric_combo.currentText()=='% of parent' else QColor('#77776f' if light else '#77777b'))
            p.drawText(QRectF(-upper_width/2,-11,upper_width,22),Qt.AlignmentFlag.AlignCenter,'of parent'); p.restore()
        axis_rect=QRectF(4,r.top(),32,r.height()) if self.export_light else self.axis_title_rect(r)
        p.setFont(title_font); p.setPen(QPen(foreground,1)); p.save()
        axis_title=self.ws.parameter.currentText() or 'Select parameter'
        if self.export_light:
            axis_title='% of parent' if self.ws.metric_combo.currentText()=='% of parent' else ('Mean' if self.ws.metric_combo.currentText()=='Mean' else 'MFI')+' · '+axis_title
        elif self.ws.metric_combo.currentText()=='% of parent': p.setPen(QColor('#77776f' if light else '#77777b'))
        axis_title=p.fontMetrics().elidedText(axis_title,Qt.TextElideMode.ElideRight,max(1,int(axis_rect.height()-14)))
        center_y=axis_rect.center().y() if self.export_light else switch.bottom()+8+p.fontMetrics().horizontalAdvance(axis_title)/2
        p.translate(axis_rect.center().x(),center_y); p.rotate(-90)
        p.drawText(QRectF(-axis_rect.height()/2,-11,axis_rect.height(),22),Qt.AlignmentFlag.AlignCenter,axis_title)
        if not self.export_light and self.ws.metric_combo.currentText()!='% of parent':
            x=-p.fontMetrics().horizontalAdvance(axis_title)/2-9; self.draw_choice_icon(p,QPointF(x,0))
        p.restore()
        if not rows:
            p.setPen(QPen(foreground,1)); p.drawLine(r.bottomLeft(),r.topLeft()); p.drawLine(r.bottomLeft(),r.bottomRight()); return
        if not groups or not values:
            message='No values for this selection' if rows else 'Open samples to compare'
            p.setPen(QColor('#666666' if light else '#aaaaaa')); p.drawText(self.rect().adjusted(40,54,0,0),Qt.AlignmentFlag.AlignCenter,message); return
        lo=min(0,min(limits)); hi=max(0,max(limits)); span=hi-lo or 1
        y=lambda v: r.bottom()-(v-lo)/span*r.height()
        p.setPen(QPen(foreground,1)); p.drawLine(r.bottomLeft(),r.topLeft()); p.drawLine(r.bottomLeft(),r.bottomRight())
        p.save(); p.setFont(tick_font(self.font()))
        for i in range(5):
            v=lo+span*i/4; yy=y(v); p.drawLine(int(r.left()-4),int(yy),int(r.left()),int(yy)); p.drawText(QRectF(38,yy-8,r.left()-44,16),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,tick_label(v))
        p.restore()
        step=r.width()/len(groups)
        for idx,group in enumerate(groups):
            vals=[r0[2] for r0 in rows if r0[1]==group and r0[2] is not None]; center=r.left()+(self.positions.get(group,idx)+.5)*step
            if not vals: continue
            mean=float(np.mean(vals)); sd=float(np.std(vals,ddof=1)) if len(vals)>1 else 0
            p.fillRect(self.bar_rect(center,step,y,mean),QColor(160,160,160,150))
            p.setPen(QPen(foreground,1.3)); p.drawLine(int(center),int(y(mean-sd)),int(center),int(y(mean+sd)))
            for yy in (y(mean-sd),y(mean+sd)): p.drawLine(int(center-5),int(yy),int(center+5),int(yy))
            for j,v in enumerate(vals):
                offset=(j/(len(vals)-1)-.5)*step*.45 if len(vals)>1 else 0
                xx=center+offset; p.setPen(Qt.PenStyle.NoPen); p.setBrush(dots); p.drawEllipse(QRectF(xx-3,y(v)-3,6,6))
            p.setPen(QPen(foreground,1)); p.drawLine(QPointF(center,r.bottom()),QPointF(center,r.bottom()+4))
            p.save(); p.setFont(tick_font(self.font())); p.translate(center,r.bottom()+8)
            label=p.fontMetrics().elidedText(group,Qt.TextElideMode.ElideRight,int(label_height if rotated else max(1,step-4)))
            if rotated: p.rotate(90); p.drawText(QRectF(0,-8,label_height,16),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,label)
            else: p.drawText(QRectF(-step/2,0,step,18),Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop,label)
            p.restore()
        preview=self.drag_preview_rect()
        if preview is not None and not self.export_light:
            p.save(); p.setClipRect(r); p.setPen(QPen(QColor(205,220,240,150),1)); p.setBrush(QColor(140,160,180,100)); p.drawRect(preview); p.restore()
        p.setFont(title_font); p.setPen(foreground); p.drawText(QRectF(r.left(),self.height()-39,r.width(),20),Qt.AlignmentFlag.AlignCenter,'Condition')
        if not self.export_light:
            p.setFont(tick_font(self.font())); p.setPen(QColor('#73736d' if light else '#99999d')); p.drawText(QRectF(r.left(),self.height()-18,r.width(),14),Qt.AlignmentFlag.AlignCenter,'Drag to rearrange')
        p.end()
    def contextMenuEvent(self,event):
        menu=QMenu(self); menu.addAction('Copy plot to clipboard',self.copy_plot); menu.exec(event.globalPos())
    def copy_plot(self):
        self.export_light=True
        try: QApplication.clipboard().setPixmap(self.grab())
        finally: self.export_light=False; self.update()
    def mousePressEvent(self,event):
        rows=self.ws.comparison_rows(); groups=self.groups(rows)
        limits=self.value_limits(rows,groups); r,_,_=self.plot_geometry(groups,limits)
        if event.button()==Qt.MouseButton.LeftButton:
            switch=self.switch_rect(r)
            if switch.contains(event.position()):
                self.switch_start=self.switch_position; self.switch_target=1. if self.ws.metric_combo.currentText()=='% of parent' else 0.; self.switch_time=time.monotonic(); self.switch_timer.start()
                self.ws.metric_combo.setCurrentText('Median' if self.switch_target==1 else '% of parent'); return
            if self.title_rect(r).contains(event.position()): self.open_choice(self.ws.pop,self.title_rect(r).bottomLeft()); return
            if self.ws.metric_combo.currentText()!='% of parent' and self.axis_title_rect(r).contains(event.position()): self.open_choice(self.ws.parameter,QPointF(r.left(),r.center().y())); return
        if groups and r.contains(event.position()) and event.button()==Qt.MouseButton.LeftButton:
            index=min(len(groups)-1,int((event.position().x()-r.left())/r.width()*len(groups)))
            vals=[row[2] for row in rows if row[1]==groups[index] and row[2] is not None]
            if not vals: return
            lo=min(0,min(limits)); hi=max(0,max(limits)); span=hi-lo or 1; y=lambda value:r.bottom()-(value-lo)/span*r.height()
            step=r.width()/len(groups); center=r.left()+(index+.5)*step
            self.drag_bar=self.bar_rect(center,step,y,float(np.mean(vals))); self.drag_origin=event.position()
            self.drag_group=groups[index]; self.drag_pos=event.position(); self.preview_order=groups[:]
            self.animation_timer.stop(); self.positions={group:float(i) for i,group in enumerate(groups)}; self.animation_to=self.positions.copy(); self.update()
    def mouseMoveEvent(self,event):
        if self.drag_group:
            self.drag_pos=event.position(); rows=self.ws.comparison_rows(); groups=self.groups(rows); r,_,_=self.plot_geometry(groups,self.value_limits(rows,groups))
            order=self.order_for_position(groups,r,event.position().x())
            if order!=self.preview_order: self.preview_order=order; self.animate_order(order)
            self.update()
        else:
            rows=self.ws.comparison_rows(); groups=self.groups(rows); r,_,_=self.plot_geometry(groups,self.value_limits(rows,groups)); pos=event.position()
            if self.switch_rect(r).contains(pos): self.setCursor(Qt.CursorShape.PointingHandCursor); self.setToolTip('Compare per-sample median or percentage of parent')
            elif self.title_rect(r).contains(pos): self.setCursor(Qt.CursorShape.PointingHandCursor); self.setToolTip('Choose population: '+(self.ws.pop.currentText() or 'All Events'))
            elif self.ws.metric_combo.currentText()!='% of parent' and self.axis_title_rect(r).contains(pos): self.setCursor(Qt.CursorShape.PointingHandCursor); self.setToolTip('Choose parameter for MFI: '+(self.ws.parameter.currentText() or 'None'))
            else: self.unsetCursor(); self.setToolTip('Drag a bar to rearrange conditions')
    def mouseReleaseEvent(self,event):
        if not self.drag_group: return
        rows=self.ws.comparison_rows(); groups=self.groups(rows)
        r,_,_=self.plot_geometry(groups,self.value_limits(rows,groups))
        order=self.order_for_position(groups,r,event.position().x()); self.animate_order(order)
        if order!=groups: self.ws.checkpoint(); self.ws.condition_order=order
        self.drag_group=None; self.drag_pos=None; self.drag_origin=None; self.drag_bar=None
        if not self.animation_timer.isActive(): self.positions={}; self.animation_to={}
        self.ws.dirty(); self.update()


class PlotDragPreview(QWidget):
    """Cached plot snapshot and destination marker above the worksheet."""
    def __init__(self,parent):
        super().__init__(parent); self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setStyleSheet('background: transparent;'); self.image=None; self.origin=QPoint(); self.destination=None; self.hide()
    def paintEvent(self,event):
        if self.image is None: return
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.destination is not None:
            painter.setPen(QPen(QColor('#438bf3'),2,Qt.PenStyle.DashLine)); painter.setBrush(QColor(55,125,230,35)); painter.drawRoundedRect(self.destination.adjusted(2,2,-2,-2),5,5)
        painter.setOpacity(.72); painter.drawPixmap(self.origin,self.image); painter.end()


class PopulationHeader(QHeaderView):
    """Draw the hierarchy headers without overriding per-column alignment."""
    def paintSection(self,painter,rect,index):
        if not rect.isValid(): return
        dark=is_dark(self); painter.save(); painter.fillRect(rect,QColor('#1d1d1f' if dark else LIGHT_WORKSHEET_BACKGROUND)); painter.setPen(QColor('#dddddd' if dark else '#292929')); painter.setFont(self.font())
        label=self.model().headerData(index,Qt.Orientation.Horizontal,Qt.ItemDataRole.DisplayRole) or ''
        alignment=Qt.AlignmentFlag.AlignBottom | (Qt.AlignmentFlag.AlignLeft if index==0 else Qt.AlignmentFlag.AlignRight)
        painter.drawText(rect.adjusted(2 if index==0 else 5,0,-5,-5),alignment,str(label)); painter.restore()


class PopulationNameDelegate(QStyledItemDelegate):
    """Indent both the gate marker and its name according to ancestry."""
    def paint(self,painter,option,index):
        opt=QStyleOptionViewItem(option)
        self.initStyleOption(opt,index); marker=index.data(Qt.ItemDataRole.UserRole+2); label=opt.text
        opt.icon=QIcon(); opt.text=''
        style=option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem,opt,painter,option.widget)
        painter.save(); painter.setFont(opt.font)
        color=opt.palette.highlightedText().color() if opt.state & QStyle.StateFlag.State_Selected else opt.palette.text().color()
        painter.setPen(color)
        x=option.rect.left()+2+11*(index.data(Qt.ItemDataRole.UserRole+1) or 0)
        if marker:
            painter.fillRect(int(x),option.rect.center().y()-4,8,8,QColor(marker)); x+=12
        width=max(0,option.rect.right()-x-2)
        text=painter.fontMetrics().elidedText(label,Qt.TextElideMode.ElideRight,width)
        painter.drawText(QRectF(x,option.rect.top(),width,option.rect.height()),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,text)
        painter.restore()


class ConditionNameEdit(QLineEdit):
    """The name opens a condition on double-click; the pencil enables editing."""
    def __init__(self, name, callback):
        super().__init__(name); self.callback=callback; self.setReadOnly(True)
        self.setStyleSheet('QLineEdit { background:transparent; border:0; padding:3px; }')
    def mouseDoubleClickEvent(self,event):
        if self.isReadOnly(): self.callback()
        else: super().mouseDoubleClickEvent(event)


class ConditionSampleDelegate(QStyledItemDelegate):
    """Draw sample names and a muted, right-aligned condition in each row."""
    def paint(self,painter,option,index):
        sample=index.data(Qt.ItemDataRole.UserRole)
        if sample is None: return super().paint(painter,option,index)
        opt=QStyleOptionViewItem(option); self.initStyleOption(opt,index)
        metrics=QFontMetricsF(opt.font); width=min(metrics.horizontalAdvance(sample.condition)+4,max(0,opt.rect.width()*.4))
        opt.text=metrics.elidedText(sample.name,Qt.TextElideMode.ElideRight,max(0,int(opt.rect.width()-width-40)))
        style=opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem,opt,painter,opt.widget)
        painter.save(); painter.setFont(opt.font); painter.setPen(QColor('#85858b'))
        text=metrics.elidedText(sample.condition,Qt.TextElideMode.ElideRight,int(width))
        painter.drawText(QRectF(opt.rect.right()-width-10,opt.rect.top(),width,opt.rect.height()),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,text)
        painter.restore()


class ConditionSampleList(QListWidget):
    """Toggle the checkbox from any point in a sample row."""
    def __init__(self):
        super().__init__(); self._pressed_item=None
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection); self.setItemDelegate(ConditionSampleDelegate(self))
    def mousePressEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if event.button()==Qt.MouseButton.LeftButton and item:
            self._pressed_item=item; self.setCurrentItem(item); event.accept(); return
        super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self._pressed_item is not None:
            item=self._pressed_item; self._pressed_item=None
            if self.itemAt(event.position().toPoint()) is item:
                item.setCheckState(Qt.CheckState.Unchecked if item.checkState()==Qt.CheckState.Checked else Qt.CheckState.Checked)
            event.accept(); return
        super().mouseReleaseEvent(event)


class Conditions(QDialog):
    def __init__(self,ws):
        super().__init__(ws); self.ws=ws; self.setWindowTitle('Assign conditions'); self.resize(820,520)
        layout=QVBoxLayout(self); layout.setContentsMargins(18,16,18,16); layout.setSpacing(12); header=QHBoxLayout(); title=QLabel('Assign conditions'); title.setObjectName('panelTitle'); header.addWidget(title); header.addStretch()
        layout.addLayout(header)
        columns=QHBoxLayout(); columns.setSpacing(28); layout.addLayout(columns,1)
        samples=QVBoxLayout(); samples.setSpacing(18); columns.addLayout(samples,3)
        heading=QHBoxLayout(); heading.addWidget(QLabel('Samples')); heading.addStretch(); samples.addLayout(heading)
        self.search=QLineEdit(); self.search.setPlaceholderText('Filter samples'); self.search.installEventFilter(self); samples.addWidget(self.search)
        self.suggestion=QPushButton(); self.suggestion.setFlat(True); self.suggestion.clicked.connect(self.complete); self.suggestion.hide(); samples.addWidget(self.suggestion)
        self.list=ConditionSampleList(); self.list.setToolTip('Click a row to select it.'); self.list.itemChanged.connect(self.selection_changed); samples.addWidget(self.list,1)
        row=QHBoxLayout(); row.addWidget(QLabel('Assign to')); self.condition=ChoiceCombo(); self.condition.setEditable(True); self.condition.lineEdit().setPlaceholderText('Choose or type a condition'); row.addWidget(self.condition,1)
        self.assign_button=QPushButton('Assign (0)'); self.assign_button.clicked.connect(self.assign); row.addWidget(self.assign_button); samples.addLayout(row)
        conditions=QVBoxLayout(); conditions.setSpacing(18); columns.addLayout(conditions,2)
        heading=QHBoxLayout(); heading.addWidget(QLabel('Conditions')); heading.addStretch(); conditions.addLayout(heading)
        hint=QLabel('Double-click a condition to open its samples in a new tab.'); hint.setObjectName('muted'); hint.setWordWrap(True); conditions.addWidget(hint)
        self.message=QLabel(''); self.message.setStyleSheet('color:#e88080'); self.message.setWordWrap(True); self.message.hide(); conditions.addWidget(self.message)
        self.conditions=QListWidget(); self.conditions.setObjectName('conditionList')
        self.conditions.setStyleSheet('QListWidget::item { padding:0; border-bottom:1px solid '+('#303033' if ws.dark else '#c9c8c1')+'; }')
        conditions.addWidget(self.conditions,1)
        actions=QHBoxLayout(); actions.addStretch()
        auto=QPushButton('Auto-Assign'); auto.setToolTip('Replace assignments using sample names without their leading well IDs'); auto.clicked.connect(self.auto); actions.addWidget(auto)
        clear_assignments=QPushButton('Clear'); clear_assignments.setToolTip('Remove all conditions and move samples to Unassigned'); clear_assignments.clicked.connect(self.clear_assignments); actions.addWidget(clear_assignments); actions.addStretch(); conditions.addLayout(actions)
        add_done(self,layout,default=False)
        self.search.textChanged.connect(self.filter); self.condition.lineEdit().installEventFilter(self)
        for button in self.findChildren(QPushButton): button.setAutoDefault(False)
        self.refresh()
    def refresh(self):
        checked={self.list.item(i).data(Qt.ItemDataRole.UserRole).path for i in range(self.list.count()) if self.list.item(i).checkState()==Qt.CheckState.Checked}
        destination=self.condition.currentText(); self.list.blockSignals(True); self.list.clear()
        for sample in sorted(self.ws.samples,key=lambda sample:(sample.name.casefold(),sample.path.casefold())):
            item=QListWidgetItem(sample.name); item.setData(Qt.ItemDataRole.UserRole,sample); item.setToolTip(f'{sample.name}\n{sample.condition}')
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Checked if sample.path in checked else Qt.CheckState.Unchecked); self.list.addItem(item)
        self.list.blockSignals(False)
        names=sorted(self.ws.conditions,key=str.casefold)
        self.condition.blockSignals(True); self.condition.clear(); self.condition.addItems(['Unassigned']+names); self.condition.setEditText(destination); self.condition.blockSignals(False)
        self.conditions.clear()
        for name in names:
            item=QListWidgetItem(); row=QWidget(); h=QHBoxLayout(row); h.setContentsMargins(4,2,4,2); h.setSpacing(4)
            edit=ConditionNameEdit(name,lambda n=name:self.open_condition(n)); edit.setMinimumWidth(edit.fontMetrics().horizontalAdvance(name)+18); edit.setMinimumHeight(max(28,edit.fontMetrics().height()+8)); edit.setToolTip(name); h.addWidget(edit,1)
            count=QLabel(str(sum(sample.condition==name for sample in self.ws.samples))); count.setMinimumWidth(count.fontMetrics().horizontalAdvance('000')+2); count.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter); h.addWidget(count); h.addSpacing(8)
            pencil=QPushButton('✎'); pencil.setFixedSize(28,28); pencil.setToolTip('Rename condition'); h.addWidget(pencil)
            remove=QPushButton('×'); remove.setFixedSize(28,28); remove.setToolTip('Remove condition and move its samples to Unassigned'); h.addWidget(remove)
            for button in (pencil,remove): button.setStyleSheet('QPushButton { padding:0; background:transparent; border:0; color:#a7a7aa; } QPushButton:hover { background:#38383b; color:#ffffff; border-radius:5px; }' if self.ws.dark else 'QPushButton { padding:0; background:transparent; border:0; color:#65655f; } QPushButton:hover { background:#c9c8c1; color:#222; border-radius:5px; }')
            pencil.clicked.connect(lambda checked=False,e=edit: (e.setReadOnly(False),e.setFocus(),e.selectAll()))
            edit.editingFinished.connect(lambda e=edit,old=name:self.rename(old,e))
            remove.clicked.connect(lambda checked=False,n=name:self.remove(n))
            item.setSizeHint(QSize(row.sizeHint().width(),max(36,row.sizeHint().height()+4))); self.conditions.addItem(item); self.conditions.setItemWidget(item,row)
        if self.ws.conditions:
            longest=max(self.fontMetrics().horizontalAdvance(name) for name in self.ws.conditions)
            self.conditions.setMinimumWidth(min(600,max(250,longest+120)))
            needed=longest+650
            self.resize(max(self.width(),min(needed,1400)),self.height())
        self.apply_filter(self.search.text(),select=False); self.selection_changed()
    def selected(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count()) if self.list.item(i).checkState()==Qt.CheckState.Checked]
    def show_message(self,text):
        self.message.setText(text); self.message.setVisible(bool(text))
    def selection_changed(self,*args):
        n=len(self.selected()); self.assign_button.setText(f'Assign ({n})'); self.assign_button.setEnabled(n>0)
    def suggestion_text(self):
        query=self.search.text().strip()
        if not query: return ''
        names=[condition_name(s.name) for s in self.ws.samples if query.casefold() in s.name.casefold()]
        if not names: return ''
        common=names[0]
        for name in names[1:]:
            i=0
            while i<min(len(common),len(name)) and common[i].casefold()==name[i].casefold(): i+=1
            common=common[:i]
        common=common.strip(' _-')
        return common if common and common.casefold()!=query.casefold() else ''
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.KeyPress:
            if obj is self.search and event.key()==Qt.Key.Key_Tab and self.suggestion_text(): self.complete(); return True
            if obj in (self.search,self.condition.lineEdit()) and event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter): self.assign(); return True
            if obj in (self.search,self.condition.lineEdit()) and event.key()==Qt.Key.Key_Escape:
                self.escape_action(); return True
        return super().eventFilter(obj,event)
    def escape_action(self):
        if self.search.text() or self.condition.currentText() or self.selected(): self.clear()
        else: self.reject()
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter): self.assign(); event.accept()
        elif event.key()==Qt.Key.Key_Escape: self.escape_action(); event.accept()
        else: super().keyPressEvent(event)
    def complete(self):
        suggestion=self.suggestion_text()
        if suggestion: self.search.setText(suggestion); self.search.setFocus()
    def apply_filter(self,text,select):
        query=text.strip().casefold(); self.list.blockSignals(True)
        for i in range(self.list.count()):
            item=self.list.item(i); matches=not query or query in item.data(Qt.ItemDataRole.UserRole).name.casefold(); item.setHidden(not matches)
            if select: item.setCheckState(Qt.CheckState.Checked if query and matches else Qt.CheckState.Unchecked)
        self.list.blockSignals(False); self.selection_changed()
        suggestion=self.suggestion_text(); self.suggestion.setText(suggestion+'     Tab ↹'); self.suggestion.setVisible(bool(suggestion))
    def filter(self,text):
        self.condition.setEditText(text); self.apply_filter(text,select=True)
    def assign(self):
        selected=self.selected(); typed=self.condition.currentText().strip()
        if not selected: return
        if not typed: self.show_message('Enter a condition name.'); return
        self.ws.checkpoint()
        if typed.casefold()=='unassigned': name='Unassigned'
        else:
            name=next((value for value in self.ws.conditions if value.casefold()==typed.casefold()),typed)
            if name not in self.ws.conditions: self.ws.conditions.append(name)
        for sample in selected: sample.condition=name
        self.ws.refresh(); self.refresh(); self.clear(); self.show_message('')
    def auto(self):
        if self.ws.samples: self.ws.checkpoint()
        for sample in self.ws.samples:
            name=condition_name(sample.name)
            if name.casefold()=='unassigned': name='Unassigned (condition)'
            name=next((v for v in self.ws.conditions if v.casefold()==name.casefold()),name)
            if name not in self.ws.conditions: self.ws.conditions.append(name)
            sample.condition=name
        self.ws.refresh(); self.refresh(); self.clear(); self.show_message('')
    def clear_assignments(self):
        if not (self.ws.conditions or self.ws.condition_order or any(sample.condition!='Unassigned' for sample in self.ws.samples) or any(entry.get('condition','Unassigned')!='Unassigned' for entry in self.ws.missing)): return
        self.ws.checkpoint()
        for sample in self.ws.samples: sample.condition='Unassigned'
        for entry in self.ws.missing: entry['condition']='Unassigned'
        self.ws.conditions=[]; self.ws.condition_order=[]
        self.ws.refresh(); self.refresh(); self.clear(); self.show_message('')
    def clear(self):
        self.search.clear(); self.condition.setEditText(''); self.list.blockSignals(True)
        for i in range(self.list.count()): self.list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.list.blockSignals(False); self.selection_changed()
    def rename(self,old,edit):
        if edit.isReadOnly(): return
        new=edit.text().strip()
        if not new or new.casefold()=='unassigned' or any(x.casefold()==new.casefold() and x!=old for x in self.ws.conditions):
            self.show_message('Enter a unique condition name other than Unassigned.'); edit.setFocus(); return
        if new!=old: self.ws.checkpoint()
        self.ws.conditions=[new if x==old else x for x in self.ws.conditions]
        self.ws.condition_order=[new if x==old else x for x in self.ws.condition_order]
        for sample in self.ws.samples:
            if sample.condition==old: sample.condition=new
        edit.setReadOnly(True); self.show_message(''); self.ws.refresh(); self.refresh()
    def remove(self,name):
        self.ws.checkpoint()
        self.ws.conditions=[x for x in self.ws.conditions if x!=name]; self.ws.condition_order=[x for x in self.ws.condition_order if x!=name]
        for sample in self.ws.samples:
            if sample.condition==name: sample.condition='Unassigned'
        self.ws.refresh(); self.refresh()
    def open_condition(self,name):
        host=self.ws.window()
        if not any(sample.condition==name for sample in self.ws.samples): self.show_message('This condition has no samples to open.'); return
        if isinstance(host,MainWindow): host.open_condition(self.ws,name); self.accept()


class SampleDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index): return QSize(120,42)
    def paint(self,painter,option,index):
        sample=index.data(Qt.ItemDataRole.UserRole)
        if sample is None: return super().paint(painter,option,index)
        painter.save(); selected=bool(option.state & QStyle.StateFlag.State_Selected)
        dark=is_dark(option.widget); painter.fillRect(option.rect,QColor('#1d1d1f' if dark else LIGHT_WORKSHEET_BACKGROUND))
        if selected: painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor('#215ed5')); painter.drawRoundedRect(QRectF(option.rect).adjusted(0,1,0,-1),5,5)
        painter.setFont(option.font); painter.setPen(QColor('#ffffff' if selected else '#ebebed' if dark else '#292929'))
        painter.drawText(option.rect.adjusted(6,2,-32,-19),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,sample.name)
        small=QFont(option.font); small.setPointSizeF(QToolTip.font().pointSizeF() if QToolTip.font().pointSizeF()>0 else max(7,small.pointSizeF()-1)); painter.setFont(small)
        painter.setPen(QColor('#d2d9ea' if selected else '#99999e' if dark else '#73736d'))
        painter.drawText(option.rect.adjusted(6,20,-4,-2),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,(f'{sample.condition} · ' if sample.condition!='Unassigned' else '')+f'{len(sample.events):,} events')
        ws=self.parent().ws; flags=[color for color,on in ((WARNING_COLOR,id(sample) in getattr(ws,'low_event_samples',())),(UNIQUE_COLOR,sample.path in ws.sample_gates)) if on]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.setPen(Qt.PenStyle.NoPen)
        for i,color in enumerate(flags): painter.setBrush(QColor(color)); painter.drawEllipse(QPointF(option.rect.right()-10-12*i,option.rect.center().y()),4,4)
        painter.restore()


class SampleList(QListWidget):
    """Samples drag onto each other to create overlays; files dropped here still import."""
    def __init__(self,ws):
        super().__init__(); self.ws=ws; self.drop_row=None; self.setItemDelegate(SampleDelegate(self))
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection); self.setDragEnabled(True); self.setAcceptDrops(True); self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.customContextMenuRequested.connect(self.menu)
    def selected_paths(self):
        return [item.data(Qt.ItemDataRole.UserRole).path for item in sorted(self.selectedItems(),key=self.row)]
    def mimeTypes(self): return [SAMPLE_MIME]
    def mimeData(self,items): return sample_mime(item.data(Qt.ItemDataRole.UserRole).path for item in sorted(items,key=self.row))
    def supportedDropActions(self): return Qt.DropAction.CopyAction
    def startDrag(self,actions): super().startDrag(Qt.DropAction.CopyAction)
    def target(self,e):
        item=self.itemAt(e.position().toPoint()); paths=dragged_paths(e.mimeData())
        return item if item and paths and item.data(Qt.ItemDataRole.UserRole).path not in paths else None
    def dragEnterEvent(self,e):
        if dragged_paths(e.mimeData()): e.acceptProposedAction()
        else: e.ignore()
    def dragMoveEvent(self,e):
        item=self.target(e); self.drop_row=self.row(item) if item else None; self.viewport().update()
        if item: e.acceptProposedAction()
        else: e.ignore()
    def dragLeaveEvent(self,e): self.drop_row=None; self.viewport().update()
    def dropEvent(self,e):
        item=self.target(e); paths=dragged_paths(e.mimeData()); self.drop_row=None; self.viewport().update()
        if not item: e.ignore(); return
        self.ws.create_overlay([item.data(Qt.ItemDataRole.UserRole).path]+paths); e.acceptProposedAction()
    def paintEvent(self,e):
        super().paintEvent(e)
        if self.drop_row is not None and self.item(self.drop_row): paint_drop_cue(self.viewport(),self.visualItemRect(self.item(self.drop_row)),'Create overlay',self.ws.dark)
    def menu(self,pos):
        paths=self.selected_paths(); menu=QMenu(self)
        create=menu.addAction(f'Create overlay from {len(paths)} selected' if len(paths)>1 else 'Create overlay…'); create.triggered.connect(lambda:self.ws.create_overlay(paths) if len(paths)>1 else self.ws.new_overlay_dialog())
        if self.ws.overlays and paths:
            add=menu.addMenu('Add to overlay')
            for overlay in self.ws.overlays: add.addAction(overlay['name'],lambda oid=overlay['id']:self.ws.add_to_overlay(oid,paths))
        if paths: menu.addSeparator(); menu.addAction('Use as compensation control',lambda:self.ws.move_to_controls(paths))
        menu.exec(self.viewport().mapToGlobal(pos))
    def wheelEvent(self, event):
        if self.count():
            delta=event.angleDelta().y()
            if delta:
                self.setCurrentRow(max(0,min(self.count()-1,self.currentRow()+(1 if delta<0 else -1)))); self.ws.show_worksheet()
                event.accept(); return
        super().wheelEvent(event)


class Workspace(QWidget):
    def __init__(self):
        super().__init__(); self.samples=[]; self.controls=[]; self.control_stains={}; self.compensation={'enabled':False,'channels':[],'matrix':[]}; self.main_gates=[]; self.sample_gates={}; self.plots=[]; self.active=None; self.selected_gate=None
        self.mode='select'; self.dark=True; self.backgating=False; self.project_path=None; self.save_status='unsaved'; self.missing=[]; self.annotations={}; self.conditions=[]; self.condition_order=[]; self.overlays=[]; self.current_overlay=None; self._loading=False; self.history=[]; self.future=[]; self.gate_percentages={}; self._comparison_last=None; self.plot_title_height=32; self.plot_zoom=1.; self.plot_columns=3
        self.stats_cache=StatisticsCache(calculator=lambda sample,gates,gate_id,parameter:statistics(sample,gates,gate_id,parameter))
        self._comparison_key=None; self._comparison_refs=(); self._comparison_rows=[]
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(400); self.timer.timeout.connect(self.autosave)
        self.setAcceptDrops(True)
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); self.pages=QStackedWidget(); outer.addWidget(self.pages)
        self.workspace_page=QWidget(); self.workspace_page.setObjectName('workspacePage'); self.pages.addWidget(self.workspace_page)
        main=QHBoxLayout(self.workspace_page); main.setContentsMargins(7,7,7,7); splitter=QSplitter(); splitter.setObjectName('workspaceSplitter'); splitter.setHandleWidth(7); main.addWidget(splitter)
        left=QWidget(); left.setObjectName('panelTile'); ll=QVBoxLayout(left); ll.setContentsMargins(14,12,12,14); ll.setSpacing(8)
        def section(text,tooltip,callback):
            row=QHBoxLayout(); row.setContentsMargins(0,0,0,0); label=QLabel(text); label.setStyleSheet('font-weight:bold;'); row.addWidget(label); row.addStretch()
            plus=QPushButton('+'); plus.setObjectName('mutedPlus'); plus.setToolTip(tooltip); plus.setAccessibleName(tooltip); plus.setFixedSize(24,24); plus.clicked.connect(callback); row.addWidget(plus); ll.addLayout(row)
        section('Samples','Add FCS files',self.add_files)
        self.sample_list=SampleList(self); self.sample_list.setObjectName('plainList'); self.sample_list.currentRowChanged.connect(self.sample_changed); self.sample_list.itemClicked.connect(lambda item:self.show_worksheet()); ll.addWidget(self.sample_list,4)
        self.unique_warning=QLabel(''); self.unique_warning.setWordWrap(True); self.unique_warning.setStyleSheet(f'color:{UNIQUE_COLOR}; font-size:11px;'); self.unique_warning.hide(); ll.addWidget(self.unique_warning)
        cond=QPushButton('Assign conditions'); cond.setToolTip('Assign samples to conditions (scroll or use the arrow keys in the list to move between samples)'); cond.clicked.connect(lambda:Conditions(self).exec())
        cond.setObjectName('worksheetAction'); cond.setFixedHeight(30); ll.addWidget(cond)
        self.controls_box=QWidget(); controls_layout=QVBoxLayout(self.controls_box); controls_layout.setContentsMargins(0,6,0,0); controls_layout.setSpacing(4)
        # Same divider as above Overlays; part of the box, so it only shows when controls exist.
        divider=QWidget(); divider.setObjectName('toolbarDivider'); divider.setFixedHeight(1); controls_layout.addWidget(divider); controls_layout.addSpacing(6)
        controls_title=QLabel('Controls'); controls_title.setStyleSheet('font-weight:bold;'); controls_title.setToolTip('Compensation controls: excluded from analysis'); controls_layout.addWidget(controls_title)
        self.control_list=QListWidget(); self.control_list.setObjectName('plainList'); self.control_list.setMaximumHeight(110); self.control_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.control_list.customContextMenuRequested.connect(self.control_menu); controls_layout.addWidget(self.control_list)
        self.controls_box.hide(); ll.addWidget(self.controls_box)
        line=QWidget(); line.setObjectName('toolbarDivider'); line.setFixedHeight(1); ll.addSpacing(6); ll.addWidget(line); ll.addSpacing(4)
        section('Overlays','New overlay from several samples',self.new_overlay_dialog)
        self.overlay_list=OverlayList(self); self.overlay_list.setObjectName('plainList'); self.overlay_list.itemPressed.connect(lambda item:self.show_overlay(item.data(Qt.ItemDataRole.UserRole))); self.overlay_list.itemDoubleClicked.connect(lambda item:self.rename_overlay(item.data(Qt.ItemDataRole.UserRole))); ll.addWidget(self.overlay_list,1)
        splitter.addWidget(left)
        middle=QWidget(); middle.setObjectName('panelTile'); ml=QVBoxLayout(middle); ml.setContentsMargins(1,12,1,6); ml.setSpacing(0)
        heading=QHBoxLayout(); heading.setContentsMargins(14,0,14,0); heading.setSpacing(10); title=QLabel('Worksheet'); title.setObjectName('panelTitle'); title.setFixedHeight(26); heading.addWidget(title)
        self.current_sample_label=QLabel(''); self.current_sample_label.setObjectName('muted'); self.current_sample_label.setStyleSheet('font-size:12px;'); heading.addWidget(self.current_sample_label,1)
        ml.addLayout(heading)
        head=QHBoxLayout(); head.setContentsMargins(14,8,14,4); head.setSpacing(7)
        self.tool_group=QButtonGroup(self); self.tool_buttons={}
        for number,(key,label) in enumerate([('select','Select / edit'),('zoom','Zoom'),('rectangle','Rectangle gate'),('ellipse','Ellipse gate'),('polygon','Polygon gate'),('quadrant','Quadrant gate')],1):
            button=ToolButton(key,number,label); button.clicked.connect(lambda checked=False,k=key:self.set_mode(k)); self.tool_group.addButton(button); self.tool_buttons[key]=button; head.addWidget(button)
        self.tool_buttons['select'].setChecked(True)
        def action(mode,key,tooltip,callback,checkable=False,shortcut=None):
            button=ToolButton(mode,key,tooltip,checkable,shortcut); button.clicked.connect(callback); return button
        self.undo_button=action('undo','Z','Undo last action',self.undo,shortcut='Z or ⌘Z / Ctrl+Z'); self.undo_button.setEnabled(False)
        reset=action('reset','R','Reset zoom of all plots',self.reset_zoom)
        self.backgate=action('backgate','B','Backgating: highlight gated events in parent plots',lambda:None,True); self.backgate.toggled.connect(self.toggle_backgating)
        zoom_out=action('smaller','−','Smaller plots',lambda:self.set_plot_columns(self.plot_columns+1))
        zoom_in=action('bigger','+','Bigger plots',lambda:self.set_plot_columns(self.plot_columns-1))
        self.redo_button=action('redo','X','Redo',self.redo,shortcut='X or ⇧⌘Z / Ctrl+Y'); self.redo_button.setEnabled(False)
        annotate=action('annotate','L','Annotate channel labels',self.annotate)
        self.compensation_button=action('matrix','M','Compensation matrix and controls',self.edit_compensation,True)
        self.gating_buttons=[action('unlock','U','Lock / unlock gating for this sample: unlocked edits apply only to it; locking returns it to the main gating',self.toggle_gating_lock,True),action('group','C','Apply this sample\'s gating to all samples in its condition',self.apply_gating_to_group),
            action('all','A','Apply this sample\'s gating to all samples (new main gating)',self.apply_gating_to_all)]
        self.gating_buttons[0].clicked.connect(lambda:self.update_gating_controls())
        options=action('options','','Options: save, export and relink files',lambda:None,shortcut='menu'); options.setMenu(self.options_menu())
        theme=action('theme','T','Switch app light / dark',self.toggle_theme)
        def divider():
            line=QWidget(); line.setObjectName('toolbarDivider'); line.setFixedSize(1,24); head.addSpacing(6); head.addWidget(line,0,Qt.AlignmentFlag.AlignVCenter); head.addSpacing(6)
        for group in ([reset,zoom_out,zoom_in,self.undo_button,self.redo_button],[self.backgate,annotate,self.compensation_button],self.gating_buttons):
            divider()
            for button in group: head.addWidget(button)
        head.addStretch(1); head.addWidget(options); head.addWidget(theme)
        self.toolbar_actions=[self.undo_button,self.redo_button,reset,annotate,self.backgate,self.compensation_button,zoom_out,zoom_in,*self.gating_buttons,options,theme]; self.worksheet_only=[self.backgate]
        for key,button in (('R',reset),('B',self.backgate),('L',annotate),('T',theme),('Z',self.undo_button),('X',self.redo_button),('+',zoom_in),('=',zoom_in),('-',zoom_out),('U',self.gating_buttons[0]),('C',self.gating_buttons[1]),('A',self.gating_buttons[2]),('M',self.compensation_button)):
            shortcut=QShortcut(QKeySequence(key),self); shortcut.activated.connect(button.click)
        ml.addLayout(head)
        self.sheet_stack=QStackedWidget(); sheet=QWidget(); sl=QVBoxLayout(sheet); sl.setContentsMargins(0,0,0,0); sl.setSpacing(0); self.sheet_stack.addWidget(sheet)
        self.overlay_view=OverlayView(self); self.sheet_stack.addWidget(self.overlay_view); ml.addWidget(self.sheet_stack,1); ml=sl
        self.tool_hint=QLabel('Select a gate to move or edit it.'); self.tool_hint.setObjectName('muted'); self.tool_hint.setContentsMargins(14,0,0,7); ml.addWidget(self.tool_hint)
        self.scroll=QScrollArea(); self.scroll.setFrameShape(QScrollArea.Shape.NoFrame); self.scroll.setWidgetResizable(True); self.canvas=QWidget(); self.grid=QGridLayout(self.canvas); self.grid.setContentsMargins(14,14,14,14); self.grid.setSpacing(3); self.grid.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft); self.scroll.setWidget(self.canvas); self.canvas.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.canvas.customContextMenuRequested.connect(self.worksheet_menu); self.scroll.viewport().installEventFilter(self); ml.addWidget(self.scroll,1)
        self.empty_label=QLabel('Open or drop FCS files to start'); self.empty_label.setParent(self.scroll.viewport()); self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_preview=PlotDragPreview(self.scroll.viewport())
        self.plot_scroll_timer=QTimer(self); self.plot_scroll_timer.setInterval(25); self.plot_scroll_timer.timeout.connect(self.scroll_plot_drag)
        self.plot_drag_plot=None; self.plot_drag_pointer=None; self.plot_drag_minimum_height=0
        splitter.addWidget(middle)
        sidebar=QWidget(); sidebar.setObjectName('workspacePage'); sidebar_layout=QVBoxLayout(sidebar); sidebar_layout.setContentsMargins(0,0,0,0); sidebar_layout.setSpacing(7)
        self.card=QWidget(); self.card.setObjectName('panelTile'); card_layout=QVBoxLayout(self.card); card_layout.setContentsMargins(14,12,14,12); card_layout.setSpacing(6)
        card_title=QLabel('Hierarchy'); card_title.setObjectName('panelTitle'); card_title.setFixedHeight(26); card_layout.addWidget(card_title)
        self.table=QTableWidget(0,4); self.table.setHorizontalHeader(PopulationHeader(Qt.Orientation.Horizontal,self.table)); self.table.setHorizontalHeaderLabels(['Population','Events','%\nparent','%\ntotal']); self.table.verticalHeader().hide(); self.table.setShowGrid(False); self.table.setItemDelegateForColumn(0,PopulationNameDelegate(self.table)); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive); self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch); self.table.horizontalHeader().setMinimumSectionSize(38); self.table.setColumnWidth(1,55); self.table.setColumnWidth(2,62); self.table.setColumnWidth(3,62); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.table.cellDoubleClicked.connect(self.edit_row); self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.table.customContextMenuRequested.connect(self.hierarchy_menu); card_layout.addWidget(self.table,1)
        self.table.horizontalHeader().setStyleSheet('QHeaderView, QHeaderView::section { background:#1d1d1f; color:#ddd; border:0; padding:0; }')
        self.table.horizontalHeaderItem(0).setTextAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignBottom)
        for col in range(1,4): self.table.horizontalHeaderItem(col).setTextAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignBottom)
        sidebar_layout.addWidget(self.card,1)
        right=QWidget(); right.setObjectName('panelTile'); rl=QVBoxLayout(right); rl.setContentsMargins(14,12,14,14); rl.setSpacing(8); header=QHBoxLayout(); title=QLabel('Analysis'); title.setObjectName('panelTitle'); title.setFixedHeight(26); header.addWidget(title)
        # Confirmation sits in the header's free space, so it never moves or covers the plot.
        self.export_note=QLabel(''); self.export_note.setObjectName('muted'); self.export_note.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter); self.export_note.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred); header.addWidget(self.export_note,1); header.addSpacing(4)
        self.prism_button=ExportButton('copy','Prism','Copy the values as a Prism table (one column per condition) to the clipboard'); self.prism_button.clicked.connect(lambda:self.copy_csv('wide')); header.addWidget(self.prism_button)
        self.export_button=ExportButton(); self.export_button.clicked.connect(self.export_menu); header.addWidget(self.export_button); rl.addLayout(header)
        self.pop=QComboBox(right); self.metric_combo=QComboBox(right); self.metric_combo.addItems(['Median','Mean','% of parent']); self.parameter=QComboBox(right); self.parameter.addItem('FL1-A','FL1-A')
        for combo in (self.pop,self.metric_combo,self.parameter): combo.currentIndexChanged.connect(self.comparison_changed)
        for combo in (self.pop,self.metric_combo,self.parameter): combo.hide()
        self.chart=Comparison(self); self.chart.setMaximumHeight(600); rl.addWidget(self.chart,1)
        self.event_warning=QLabel(''); self.event_warning.setWordWrap(True); self.event_warning.setAlignment(Qt.AlignmentFlag.AlignCenter); self.event_warning.setStyleSheet(f'color:{WARNING_COLOR}; font-size:11px;'); self.event_warning.hide(); rl.addWidget(self.event_warning)
        self.export_note_timer=QTimer(self); self.export_note_timer.setSingleShot(True); self.export_note_timer.setInterval(5000); self.export_note_timer.timeout.connect(lambda:(self.export_note.setText(''),self.export_note.setToolTip('')))
        sidebar_layout.addWidget(right,1); splitter.addWidget(sidebar); splitter.setSizes([220,1000,360]); self.apply_theme()
        self.new_plot(None)
        self.welcome_page=self.make_welcome(); self.pages.addWidget(self.welcome_page); self.pages.setCurrentWidget(self.welcome_page)
        for key,mode in [('1','select'),('2','zoom'),('3','rectangle'),('4','ellipse'),('5','polygon'),('6','quadrant')]:
            shortcut=QShortcut(QKeySequence(key),self); shortcut.activated.connect(self.tool_buttons[mode].click)
        for key in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace):
            shortcut=QShortcut(QKeySequence(key),self.table); shortcut.setContext(Qt.ShortcutContext.WidgetShortcut); shortcut.activated.connect(self.delete_selected_row)
        undo_shortcut=QShortcut(QKeySequence(QKeySequence.StandardKey.Undo),self); undo_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut); undo_shortcut.activated.connect(self.undo)
        redo_shortcut=QShortcut(QKeySequence(QKeySequence.StandardKey.Redo),self); redo_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut); redo_shortcut.activated.connect(self.redo)
    def showEvent(self,event):
        super().showEvent(event); QApplication.instance().installEventFilter(self)
    def hideEvent(self,event):
        QApplication.instance().removeEventFilter(self); super().hideEvent(event)
    def make_welcome(self):
        # Same frame as the workspace: dark page, 7 px margins, one rounded tile.
        page=QWidget(); page.setObjectName('workspacePage'); outer=QVBoxLayout(page); outer.setContentsMargins(7,7,7,7)
        tile=QWidget(); tile.setObjectName('panelTile'); outer.addWidget(tile); layout=QVBoxLayout(tile); layout.addStretch(); center=QWidget(); center.setMaximumWidth(720); content=QVBoxLayout(center); content.setSpacing(14)
        title=QLabel('Welcome to Cytose'); title.setStyleSheet('font-size:20px; font-weight:bold'); content.addWidget(title)
        content.addWidget(QLabel('Choose how to start your analysis.'))
        choices=QHBoxLayout(); choices.setSpacing(12)
        for title,description,action in [
            ('Open project','Continue an existing Cytose project.',self.open_project_here),
            ('New project','Choose where to save. FCS files in that folder open automatically.',self.new_project),
            ('Quick analysis','Start without saving. Add FCS files when you are ready.',self.show_workspace)]:
            button=WelcomeChoice(title,description); button.clicked.connect(action); choices.addWidget(button,1)
        content.addLayout(choices)
        layout.addWidget(center,0,Qt.AlignmentFlag.AlignHCenter); layout.addStretch(); return page
    def show_workspace(self):
        self.pages.setCurrentWidget(self.workspace_page)
        self.update_tab_title()
    def open_project_here(self):
        path,_=remembered(QFileDialog.getOpenFileName(self,'Open project',start_folder(),'Cytose project (*.cytose)'))
        if not path: return
        try: self.load_project(path)
        except (OSError,ValueError,KeyError,TypeError) as exc: QMessageBox.warning(self,'Could not open project',str(exc)); return
        self.show_workspace(); self.update_tab_title()
    def new_project(self):
        path,_=remembered(QFileDialog.getSaveFileName(self,'Create project',new_project_name(),'Cytose project (*.cytose)'))
        if not path: return
        self.project_path=path if path.lower().endswith('.cytose') else path+'.cytose'
        if not self.autosave(): self.project_path=None; self.set_save_status('unsaved'); return
        self.show_workspace(); self.import_paths([str(Path(self.project_path).parent)]); self.update_tab_title()
    def update_tab_title(self):
        host=self.window()
        if isinstance(host,MainWindow):
            index=host.tabs.indexOf(self)
            if index>=0:
                host.tabs.setTabText(index,Path(self.project_path).stem if self.project_path else '(unsaved)')
                host.tabs.tabBar().set_save_status(index,self.save_status)
    def set_save_status(self,status):
        self.save_status=status
        host=self.window()
        if isinstance(host,MainWindow):
            index=host.tabs.indexOf(self)
            if index>=0: host.tabs.tabBar().set_save_status(index,status)
    def options_menu(self):
        menu=QMenu(self); menu.addAction('Save project',self.save_project); menu.addAction('Save project as',lambda:self.save_project(True)); menu.addAction('Export plot PNG',self.export_plot); menu.addAction('Copy plot',lambda:self.copy_plot(self.active)); menu.addAction('Export worksheet PDF',self.export_worksheet); menu.addAction('Relink missing files',self.relink_missing); return menu
    def eventFilter(self, watched, event):
        # Only widget presses count: the same click also passes through the window object first.
        if event.type()==QEvent.Type.MouseButtonPress and isinstance(watched,QWidget) and (self.selected_gate or any(plot.selected for plot in self.plots)):
            keep=None
            if isinstance(watched,ScatterPlot) and watched in self.plots and watched.bounds and (watched.plot_rect().adjusted(-1,-1,1,1).contains(event.position()) or watched.on_selected_handle(event.position())):
                gate,_=watched.gate_at(event.position())
                selected=next((g for g in self.gates if g.id==watched.selected),None)
                if (gate and gate==watched.selected) or watched.quadrant_handle_at(selected,event.position()): keep=watched
            for plot in self.plots:
                if plot is not keep and plot.selected is not None:
                    plot.selected=None; plot.edit_vertex=None; plot.edit_edge=None; plot.update()
            if keep is None: self.selected_gate=None
        if hasattr(self, 'scroll') and watched is self.scroll.viewport() and event.type()==QEvent.Type.Resize:
            if hasattr(self,'plot_preview'): self.plot_preview.setGeometry(self.scroll.viewport().rect())
            QTimer.singleShot(0,self.layout_plots); QTimer.singleShot(0,self.position_card)
        return super().eventFilter(watched,event)
    def position_card(self):
        available=self.scroll.viewport().size()
        self.empty_label.setGeometry(0,max(0,available.height()//2-20),available.width(),40)
        if not self.samples: self.empty_label.raise_()
    def apply_theme(self):
        bg=DARK_WORKSHEET_BACKGROUND if self.dark else LIGHT_WORKSHEET_BACKGROUND
        self.setStyleSheet(STYLE if self.dark else LIGHT_STYLE)
        self.table.horizontalHeader().setStyleSheet(f'QHeaderView, QHeaderView::section {{ background:{bg}; border:0; padding:0; }}')
        # Selector-scoped so the background does not cascade into menus opened from plots.
        self.canvas.setObjectName('plotCanvas'); self.scroll.viewport().setObjectName('plotViewport')
        self.canvas.setStyleSheet(f'QWidget#plotCanvas {{ background:{bg}; }}'); self.scroll.viewport().setStyleSheet(f'QWidget#plotViewport {{ background:{bg}; }}')
        self.empty_label.setStyleSheet(f'background:{bg}; color:{"#aaa" if self.dark else "#777"}; font-size:13px;')
        host=self.window()
        if isinstance(host,MainWindow) and host.tabs.currentWidget() is self: host.apply_current_theme()
        self.chart.update(); self.table.viewport().update(); self.table.horizontalHeader().update(); self.sample_list.viewport().update(); self.overlay_list.viewport().update(); self.overlay_view.graph.update()
        for plot in self.plots: plot.update()
    def layout_plots(self):
        if not hasattr(self,'scroll'): return
        columns=self.plot_columns
        width=max(1,(self.scroll.viewport().width()-28-3*(columns-1))//columns)
        self.plot_zoom=width/320
        for plot in self.plots:
            font=QFont(self.font())
            if font.pointSizeF()>0: font.setPointSizeF(font.pointSizeF()*self.plot_zoom)
            elif font.pixelSize()>0: font.setPixelSize(max(1,round(font.pixelSize()*self.plot_zoom)))
            plot.setFont(font)
        title_heights=[title_layout(plot.title_text(),plot.font(),max(1,width-105*self.plot_zoom))[1] for plot in self.plots]
        self.plot_title_height=max([math.ceil(32*self.plot_zoom)]+[math.ceil(height+8*self.plot_zoom) for height in title_heights])
        height=self.plot_title_height+round(283*self.plot_zoom)
        for col in range(self.grid.columnCount()): self.grid.setColumnMinimumWidth(col,0)
        for row in range(self.grid.rowCount()): self.grid.setRowMinimumHeight(row,0)
        for plot in self.plots: self.grid.removeWidget(plot)
        rows=max((plot.grid_slot//columns+1 for plot in self.plots),default=1)
        for col in range(columns): self.grid.setColumnMinimumWidth(col,width)
        for row in range(rows): self.grid.setRowMinimumHeight(row,height)
        for plot in self.plots:
            plot.setFixedSize(width,height); self.grid.addWidget(plot,plot.grid_slot//columns,plot.grid_slot%columns)
    def duplicate_plot(self,plot):
        """Copy a plot (population, axes, zoom) into the next free grid spot."""
        if plot not in self.plots: return
        self.checkpoint(); self.new_plot(plot.population,plot.x,plot.y,copy.deepcopy(plot.bounds)); self.refresh()
    def refresh_controls(self):
        if not hasattr(self,'control_list'): return
        self.control_list.clear()
        for control in self.controls:
            stain=self.control_stains.get(control.path); item=QListWidgetItem(control.name+('  ·  '+('unstained' if stain=='unstained' else stain) if stain else ''))
            item.setData(Qt.ItemDataRole.UserRole,control.path); item.setToolTip(control.name+'\nCompensation control: not used in analysis'); self.control_list.addItem(item)
        self.controls_box.setVisible(bool(self.controls)); self.compensation_button.setChecked(bool(self.compensation.get('enabled')))
    def move_to_controls(self,paths):
        """Compensation controls leave the analysis entirely (plots, statistics, overlays, warnings)."""
        from .compensation import guess_stain, stain_choices
        moving=[s for s in self.samples if s.path in set(paths)]
        if not moving: return
        self.checkpoint(); choices=stain_choices(self.samples+self.controls)
        for sample in moving:
            self.samples.remove(sample); self.controls.append(sample); self.sample_gates.pop(sample.path,None)
            guess=guess_stain(sample.name,choices)
            if guess: self.control_stains[sample.path]=guess
            for overlay in self.overlays: overlay['entries']=[e for e in overlay['entries'] if e['path']!=sample.path]
        self.controls.sort(key=lambda s:natural_key(s.name)); self.apply_compensation(); self.refresh()
    def move_to_samples(self,paths):
        moving=[s for s in self.controls if s.path in set(paths)]
        if not moving: return
        self.checkpoint()
        for sample in moving: self.controls.remove(sample); self.samples.append(sample); self.control_stains.pop(sample.path,None)
        self.samples.sort(key=lambda s:natural_key(s.name)); self.apply_compensation(); self.refresh()
    def control_menu(self,pos):
        item=self.control_list.itemAt(pos)
        if not item: return
        menu=QMenu(self.control_list); menu.addAction('Move back to samples',lambda:self.move_to_samples([item.data(Qt.ItemDataRole.UserRole)])); menu.addAction('Compensation…',self.edit_compensation)
        menu.exec(self.control_list.viewport().mapToGlobal(pos))
    def apply_compensation(self):
        """Compensated events for every analysis sample; raw values come back when switched off."""
        settings=self.compensation; on=bool(settings.get('enabled')) and bool(settings.get('channels'))
        # Only area channels are compensated, also for matrices saved with height channels.
        keep=[i for i,name in enumerate(settings.get('channels') or []) if re.search(r'[-_ ]A$',name.strip())] or list(range(len(settings.get('channels') or [])))
        channels=[settings['channels'][i] for i in keep]; matrix=np.array(settings.get('matrix') or np.eye(len(keep)),dtype=float)[np.ix_(keep,keep)] if keep else None
        for sample in self.samples+self.controls:
            if sample.raw is not None: sample.events=sample.raw; sample.raw=None
            if on and sample in self.samples:
                raw=sample.events; sample.raw=raw; sample.events=compensate(sample,channels,matrix)
                if sample.events is raw: sample.raw=None
        if hasattr(self,'compensation_button'): self.compensation_button.setChecked(on)
    def edit_compensation(self):
        from .compensation import CompensationDialog
        dialog=CompensationDialog(self); accepted=dialog.exec(); self.compensation_button.setChecked(bool(self.compensation.get('enabled')))
        if not accepted: return
        settings,stains=dialog.result()
        if settings==self.compensation and stains==self.control_stains: return
        self.checkpoint(); self.compensation=settings; self.control_stains=stains; self.apply_compensation(); self.refresh()
    def worksheet_menu(self,pos):
        """Right-click on empty worksheet space."""
        if not self.samples: return
        menu=QMenu(self.canvas); menu.addAction('New All Events plot',self.add_all_events_plot); menu.exec(self.canvas.mapToGlobal(pos))
    def add_all_events_plot(self):
        self.checkpoint(); self.new_plot(None); self.refresh()
    def set_plot_columns(self,value):
        value=max(1,min(5,int(value)))
        if value==self.plot_columns: return
        self.checkpoint(); self.plot_columns=value; self.layout_plots(); self.overlay_view.graph.update(); self.dirty()
    def plot_drop_slot(self,plot,global_pos):
        point=self.canvas.mapFromGlobal(global_pos)
        columns=self.plot_columns
        if not self.scroll.viewport().rect().contains(self.scroll.viewport().mapFromGlobal(global_pos)): return None
        col=max(0,min(columns-1,(point.x()-14)//(plot.width()+3)))
        row=max(0,(point.y()-14)//(plot.height()+3))
        return row*columns+col
    def begin_plot_preview(self,plot,press_pos):
        self.plot_drag_plot=plot; self.plot_drag_minimum_height=self.canvas.minimumHeight()
        self.plot_preview.image=plot.grab(); self.plot_preview.offset=press_pos.toPoint()-plot.mapToGlobal(QPoint())
        self.plot_preview.setGeometry(self.scroll.viewport().rect()); self.plot_preview.show(); self.plot_preview.raise_()
    def update_plot_preview(self,plot,global_pos):
        self.plot_drag_pointer=global_pos
        if not self.plot_scroll_timer.isActive(): self.plot_scroll_timer.start()
        preview=self.plot_preview; preview.origin=self.scroll.viewport().mapFromGlobal(global_pos-preview.offset)
        slot=self.plot_drop_slot(plot,global_pos)
        if slot is None: preview.destination=None
        else:
            columns=self.plot_columns; row,col=divmod(slot,columns)
            pos=self.scroll.viewport().mapFromGlobal(self.canvas.mapToGlobal(QPoint(14+col*(plot.width()+3),14+row*(plot.height()+3))))
            preview.destination=QRectF(pos.x(),pos.y(),plot.width(),plot.height())
        preview.update()
    def scroll_plot_drag(self):
        plot=self.plot_drag_plot; pointer=self.plot_drag_pointer
        if plot is None or pointer is None: return
        viewport=self.scroll.viewport(); local=viewport.mapFromGlobal(pointer); margin=48
        if local.x()<0 or local.x()>=viewport.width(): return
        if local.y()<margin: direction=-1; proximity=margin-local.y()
        elif local.y()>viewport.height()-margin: direction=1; proximity=local.y()-(viewport.height()-margin)
        else: return
        bar=self.scroll.verticalScrollBar()
        if direction>0 and bar.value()>=bar.maximum()-8:
            self.canvas.setMinimumHeight(self.canvas.height()+plot.height()+3)
        bar.setValue(bar.value()+direction*max(4,min(24,4+proximity//3)))
        self.update_plot_preview(plot,pointer)
    def end_plot_preview(self):
        self.plot_scroll_timer.stop(); self.plot_drag_plot=None; self.plot_drag_pointer=None
        self.canvas.setMinimumHeight(self.plot_drag_minimum_height)
        self.plot_preview.hide(); self.plot_preview.image=None; self.plot_preview.destination=None
    def move_plot(self,plot,global_pos):
        if plot not in self.plots: return
        slot=self.plot_drop_slot(plot,global_pos)
        if slot is None: return
        if slot==plot.grid_slot: return
        self.checkpoint()
        other=next((p for p in self.plots if p is not plot and p.grid_slot==slot),None)
        if other: other.grid_slot=plot.grid_slot
        plot.grid_slot=slot
        self.layout_plots(); self.dirty()
    def checkpoint(self):
        if self._loading: return
        self.history.append(self.capture_state()); self.future=[]
        if len(self.history)>40: self.history.pop(0)
        self.undo_button.setEnabled(True); self.redo_button.setEnabled(False)
    def capture_state(self):
        return {'samples':self.samples[:], 'sample_conditions':[(s,s.condition) for s in self.samples], 'missing':copy.deepcopy(self.missing),
            'gates':copy.deepcopy(self.main_gates), 'sample_gates':copy.deepcopy(self.sample_gates), 'controls':self.controls[:], 'control_stains':dict(self.control_stains), 'compensation':copy.deepcopy(self.compensation), 'conditions':self.conditions[:], 'condition_order':self.condition_order[:],
            'annotations':self.annotations.copy(), 'dark':self.dark, 'backgating':self.backgating, 'overlays':copy.deepcopy(self.overlays), 'current_overlay':self.current_overlay,
            'plots':[(p.population,p.x,p.y,copy.deepcopy(p.bounds),p.grid_slot) for p in self.plots], 'plot_columns':self.plot_columns,
            'active':self.plots.index(self.active) if self.active in self.plots else 0,
            'selected':self.sample_list.currentRow(), 'parameter':self.parameter.currentData(),
            'population':self.pop.currentData(), 'metric':self.metric_combo.currentText()}
    def undo(self):
        if not self.history: return
        self.future.append(self.capture_state()); self.restore_state(self.history.pop())
    def redo(self):
        if not self.future: return
        self.history.append(self.capture_state()); self.restore_state(self.future.pop())
    def restore_state(self,state):
        self._loading=True
        self.samples=state['samples']
        self.missing=state['missing']
        for sample,condition in state['sample_conditions']: sample.condition=condition
        self.main_gates=state['gates']; self.sample_gates=state.get('sample_gates',{}); self.controls=state.get('controls',[]); self.control_stains=state.get('control_stains',{}); self.compensation=state.get('compensation',self.compensation); self.apply_compensation(); self.conditions=state['conditions']; self.condition_order=state['condition_order']; self.annotations=state['annotations']; self.dark=state['dark']; self.plot_columns=state.get('plot_columns',3); self.apply_theme(); self.backgate.setChecked(state['backgating'])
        for plot in self.plots: self.grid.removeWidget(plot); plot.deleteLater()
        self.plots=[]
        for population,x,y,bounds,slot in state['plots']: self.new_plot(population,x,y,bounds,slot)
        if not self.plots: self.new_plot(None)
        self.active=self.plots[min(state['active'],len(self.plots)-1)]; self.refresh()
        self.sample_list.setCurrentRow(min(state['selected'],len(self.samples)-1))
        self.parameter.setCurrentIndex(max(0,self.parameter.findData(state['parameter']))); self.pop.setCurrentIndex(max(0,self.pop.findData(state['population']))); self.metric_combo.setCurrentText(state['metric'])
        self.chart.switch_position=0. if self.metric_combo.currentText()=='% of parent' else 1.
        self.overlays=state['overlays']; self.restore_overlay(state['current_overlay'])
        self.selected_gate=None; self.set_mode('select'); self._loading=False; self.undo_button.setEnabled(bool(self.history)); self.redo_button.setEnabled(bool(self.future)); self.refresh(); self.dirty()
    def reset_zoom(self):
        if self.current_overlay: self.overlay_view.graph.zoom_stack=[]; self.overlay_view.set_zoom(None); return
        self.checkpoint()
        for plot in self.plots: plot.zoom_history=[]; plot.reset()
        self.dirty()
    def axis_label(self,name):
        label=self.annotations.get(name,'').strip()
        return f'{name} · {label}' if label and label.casefold()!=name.strip().casefold() else name
    def annotate(self):
        sample=self.sample()
        if not sample: return
        dialog=QDialog(self); dialog.setWindowTitle('Annotate labels'); layout=QVBoxLayout(dialog); layout.setContentsMargins(18,16,18,14); form=QFormLayout(); fields={}
        for p in sample.parameters:
            field=QLineEdit(self.annotations.get(p.name,'')); fields[p.name]=field; form.addRow(p.name,field)
        layout.addLayout(form); clear_all=[False]; clear=QPushButton('Clear all labels')
        def clear_labels():
            clear_all[0]=True
            for field in fields.values(): field.clear()
        clear.clicked.connect(clear_labels); layout.addWidget(clear)
        add_done(dialog,layout)
        if dialog.exec():
            self.checkpoint(); self.annotations={name:field.text().strip() for name,field in fields.items() if field.text().strip()} | ({} if clear_all[0] else {name:value for name,value in self.annotations.items() if name not in fields})
            self.refresh()
    def set_mode(self,mode):
        self.mode=mode; self.tool_buttons[mode].setChecked(True)
        self.tool_hint.setText({'select':'Select a gate to move or edit it.','zoom':'Drag across a plot to zoom; double-click to go back one level.','rectangle':'Drag to draw a rectangular gate.','ellipse':'Drag to draw an elliptical gate; drag its handles to resize, or the round handle to rotate.','polygon':'Click to add points; double-click to finish.','quadrant':'Click to place a quadrant gate.'}[mode])
    def toggle_backgating(self,checked):
        if checked!=self.backgating: self.checkpoint()
        self.backgating=checked
        for p in self.plots: p.update()
        self.dirty()
    def toggle_theme(self):
        self.checkpoint()
        self.dark=not self.dark
        self.apply_theme()
        self.refresh_table()
        self.dirty()
    def step(self,delta): self.sample_list.setCurrentRow(max(0,min(self.sample_list.count()-1,self.sample_list.currentRow()+delta))); self.show_worksheet()
    def sample(self):
        i=self.sample_list.currentRow(); return self.samples[i] if 0<=i<len(self.samples) else None
    def sample_changed(self,index):
        self.update_sample_label()
        for p in self.plots: p.setVisible(bool(self.samples)); p.update()
        self.empty_label.setVisible(not self.samples); self.position_card()
        self.refresh_table(); self.dirty()
    def add_files(self):
        paths,_=remembered(QFileDialog.getOpenFileNames(self,'Open FCS files',start_folder(),'FCS files (*.fcs *.FCS)')); self.import_paths(paths)
    def import_paths(self,paths):
        if paths: self.show_workspace()
        errors=[]; additions=[]
        for raw in paths:
            path=Path(raw); files=list(path.rglob('*')) if path.is_dir() else [path]
            for file in files:
                if not file.is_file() or file.suffix.lower()!='.fcs' or any(s.path==str(file.resolve()) for s in self.samples+additions): continue
                try: additions.append(read_fcs(file))
                except (OSError,ValueError) as exc: errors.append(f'{file.name}: {exc}')
        if additions: self.checkpoint(); self.samples.extend(additions); self.apply_compensation(); self.samples.sort(key=lambda s:natural_key(s.name))
        self.refresh()
        if self.sample_list.currentRow()<0 and self.samples: self.sample_list.setCurrentRow(0)
        if errors: QMessageBox.warning(self,'Import errors','\n'.join(errors))
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self,e): self.import_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]); e.acceptProposedAction()
    def refresh(self):
        for sample in self.samples:
            if sample.condition!='Unassigned' and sample.condition not in self.conditions: self.conditions.append(sample.condition)
        index=self.sample_list.currentRow(); self.sample_list.blockSignals(True); self.sample_list.clear()
        for s in self.samples:
            item=QListWidgetItem(s.name); item.setData(Qt.ItemDataRole.UserRole,s); item.setToolTip(s.name); self.sample_list.addItem(item)
        self.sample_list.setCurrentRow(min(max(index,0),len(self.samples)-1)); self.sample_list.blockSignals(False)
        self.update_sample_label()
        prev_pop=self.pop.currentData(); prev_parameter=self.parameter.currentData()
        self.pop.blockSignals(True); self.pop.clear(); self.pop.addItem('All Events',None)
        for g in self.gates: self.pop.addItem(self.population_name(g.id),g.id)
        self.pop.setCurrentIndex(max(0,self.pop.findData(prev_pop))); self.pop.blockSignals(False)
        self.parameter.blockSignals(True); self.parameter.clear()
        names=list(dict.fromkeys(p.name for s in self.samples for p in s.parameters))
        if not names and not self.samples: names=['FL1-A']
        for name in names: self.parameter.addItem(self.annotations.get(name,'').strip() or name,name)
        selected=self.parameter.findData(prev_parameter or 'FL1-A')
        if selected<0: selected=self.parameter.findData('FL1-A')
        self.parameter.setCurrentIndex(max(0,selected)); self.parameter.blockSignals(False)
        self.layout_plots()
        for p in self.plots: p.setVisible(bool(self.samples)); p.update()
        self.empty_label.setVisible(not self.samples); self.position_card()
        self.refresh_controls(); self.refresh_table(); self.refresh_comparison(); self.refresh_overlay_list(); self.update_sample_label()
        if self.current_overlay: self.overlay_view.refresh()
        self.dirty()
    def population_name(self,gid):
        gate=next((g for g in self.gates if g.id==gid),None)
        if gate is None: return 'All Events'
        names=[gate.name]; parent=gate.parent; seen=set()
        while parent and parent not in seen:
            seen.add(parent); ancestor=next((a for a in self.gates if a.id==parent),None)
            if not ancestor: break
            names.insert(0,ancestor.name); parent=ancestor.parent
        return ' / '.join(names)
    def update_sample_label(self):
        overlay=self.overlay(self.current_overlay); sample=self.sample()
        self.current_sample_label.setText(overlay['name'] if overlay else (sample.name+('  ·  unique gating' if sample.path in self.sample_gates else '')) if sample else '')
        self.update_gating_controls()
    def overlay(self,oid): return next((o for o in self.overlays if o['id']==oid),None)
    @property
    def gates(self):
        """Gates for the displayed sample: its own copy when unlocked, otherwise the main gating."""
        sample=self.sample() if hasattr(self,'sample_list') else None
        return self.sample_gates.get(sample.path,self.main_gates) if sample else self.main_gates
    @gates.setter
    def gates(self,value):
        sample=self.sample() if hasattr(self,'sample_list') else None
        if sample and sample.path in self.sample_gates: self.sample_gates[sample.path]=value
        else: self.main_gates=value
    def gates_for(self,sample): return self.sample_gates.get(sample.path,self.main_gates)
    def toggle_gating_lock(self):
        sample=self.sample()
        if sample and sample.path in self.sample_gates: self.reset_gating()
        else: self.unlock_gating()
    def unlock_gating(self):
        sample=self.sample()
        if not sample or sample.path in self.sample_gates: return
        self.checkpoint(); self.sample_gates[sample.path]=copy.deepcopy(self.main_gates); self.refresh()
    def apply_gating_to_group(self):
        sample=self.sample()
        if not sample or sample.condition=='Unassigned': return
        group=[s for s in self.samples if s.condition==sample.condition]
        if len(group)==len(self.samples): self.apply_gating_to_all(); return
        self.checkpoint(); current=self.gates
        for member in group: self.sample_gates[member.path]=copy.deepcopy(current)
        self.refresh()
    def apply_gating_to_all(self):
        if not self.sample(): return
        self.checkpoint(); self.main_gates=copy.deepcopy(self.gates); self.sample_gates={}; self.refresh()
    def reset_gating(self):
        sample=self.sample()
        if not sample or sample.path not in self.sample_gates: return
        self.checkpoint(); del self.sample_gates[sample.path]; self.refresh()
    def update_gating_controls(self):
        if not hasattr(self,'gating_buttons'): return
        sample=self.sample(); unique=bool(sample) and sample.path in self.sample_gates; enabled=bool(sample) and not self.current_overlay
        unlock,group,every=self.gating_buttons
        unlock.setChecked(unique); unlock.setEnabled(enabled); group.setEnabled(enabled and sample.condition!='Unassigned'); every.setEnabled(enabled)
        count=sum(s.path in self.sample_gates for s in self.samples)
        self.unique_warning.setText(f'● {count} sample{"s" if count!=1 else ""} with unique gating'); self.unique_warning.setVisible(bool(count))
        self.sample_list.viewport().update()
    def refresh_overlay_list(self):
        self.overlay_list.blockSignals(True); self.overlay_list.clear()
        for overlay in self.overlays:
            item=QListWidgetItem(overlay['name']); item.setData(Qt.ItemDataRole.UserRole,overlay['id']); item.setToolTip(overlay['name']); self.overlay_list.addItem(item)
            if overlay['id']==self.current_overlay: item.setSelected(True); self.overlay_list.setCurrentItem(item)
        self.overlay_list.blockSignals(False)
    def show_worksheet(self):
        if self.current_overlay is None: return
        self.current_overlay=None; self.sheet_stack.setCurrentIndex(0); self.overlay_list.clearSelection()
        for button in list(self.tool_buttons.values())+self.worksheet_only: button.setEnabled(True)
        self.update_sample_label(); self.dirty()
    def show_overlay(self,oid):
        if not self.overlay(oid): return
        self.current_overlay=oid; self.sheet_stack.setCurrentWidget(self.overlay_view); self.overlay_view.show_overlay(oid); self.refresh_overlay_list()
        for button in list(self.tool_buttons.values())+self.worksheet_only: button.setEnabled(False)
        self.update_sample_label(); self.dirty()
    def show_sample(self,path):
        row=next((i for i,s in enumerate(self.samples) if s.path==path),None)
        if row is not None: self.sample_list.setCurrentRow(row); self.show_worksheet()
    def restore_overlay(self,oid):
        if self.overlay(oid): self.show_overlay(oid)
        else: self.show_worksheet()
        self.refresh_overlay_list()
    def overlay_changed(self):
        self.refresh_overlay_list(); self.update_sample_label(); self.dirty()
    def overlay_defaults(self):
        plot=self.active; x=self.parameter.currentData() or 'FL1-A'
        return dict(x=x,y=plot.y if plot and plot.y and plot.y!=HISTOGRAM else 'SSC-A',population=plot.population if plot else None)
    def create_overlay(self,paths,name=None):
        known={s.path for s in self.samples}; paths=[path for path in dict.fromkeys(paths) if path in known]
        if not paths: return None
        names={o['name'] for o in self.overlays}; number=len(self.overlays)+1
        while f'Overlay {number}' in names: number+=1
        self.checkpoint(); overlay=new_overlay(name or f'Overlay {number}',paths,**self.overlay_defaults()); self.overlays.append(overlay)
        self.show_overlay(overlay['id']); return overlay['id']
    def add_to_overlay(self,oid,paths):
        overlay=self.overlay(oid); known={s.path for s in self.samples}
        if not overlay: return
        paths=[path for path in paths if path in known and path not in {e['path'] for e in overlay['entries']}]
        if not paths: return
        self.checkpoint(); add_entries(overlay,paths)
        if self.current_overlay==oid: self.overlay_view.refresh()
        self.overlay_changed()
    def new_overlay_dialog(self):
        if not self.samples: return
        names={o['name'] for o in self.overlays}; number=len(self.overlays)+1
        while f'Overlay {number}' in names: number+=1
        dialog=SampleChooser(self,'New overlay',self.samples,set(self.sample_list.selected_paths()),f'Overlay {number}')
        if dialog.exec() and dialog.paths(): self.create_overlay(dialog.paths(),dialog.name.text().strip() or None)
    def rename_overlay(self,oid):
        overlay=self.overlay(oid)
        if not overlay: return
        name=ask_name(self,'Rename overlay',overlay['name'])
        if name and name!=overlay['name']:
            self.checkpoint(); overlay['name']=name
            if self.current_overlay==oid: self.overlay_view.graph.update()
            self.overlay_changed()
    def duplicate_overlay(self,oid):
        overlay=self.overlay(oid)
        if not overlay: return
        self.checkpoint(); duplicate=copy.deepcopy(overlay); duplicate.update(id=str(uuid.uuid4()),name=overlay['name']+' copy')
        self.overlays.insert(self.overlays.index(overlay)+1,duplicate); self.show_overlay(duplicate['id'])
    def remove_overlay(self,oid):
        overlay=self.overlay(oid)
        if not overlay: return
        self.checkpoint(); self.overlays.remove(overlay)
        if self.current_overlay==oid: self.show_worksheet()
        self.overlay_changed()
    def new_plot(self,population,x=None,y=None,bounds=None,slot=None):
        p=ScatterPlot(self,population,x,y); p.bounds=bounds
        used={plot.grid_slot for plot in self.plots}; p.grid_slot=slot if slot is not None else next(i for i in range(len(used)+1) if i not in used)
        p.changed.connect(self.refresh); p.opened.connect(self.open_gate); p.activated.connect(self.activate_plot); p.editRequested.connect(self.edit_gate); p.closeRequested.connect(self.close_plot); self.plots.append(p); self.layout_plots(); p.setVisible(bool(self.samples)); self.active=p
    def activate_plot(self,plot):
        self.active=plot
        for item in self.plots: item.update()
        self.refresh_table(); self.dirty()
    def close_plot(self,plot):
        if plot not in self.plots or len(self.plots)<2: return
        self.checkpoint()
        self.plots.remove(plot); self.grid.removeWidget(plot); plot.deleteLater()
        if self.active is plot: self.active=self.plots[0]
        self.layout_plots(); self.refresh()
    def add_gate(self,plot,vertices,shape=None):
        self.checkpoint(); gate=Gate(default_gate_name(plot.x,plot.y,[g.name for g in self.gates]),plot.x,plot.y,vertices,plot.population,shape=shape); self.gates.append(gate); self.selected_gate=gate.id; self.set_mode('select'); self.refresh()
    def add_quadrants(self,plot,point):
        self.checkpoint()
        group=str(uuid.uuid4())
        for hx,hy,label in [(False,True,'Q1'),(True,True,'Q2'),(True,False,'Q3'),(False,False,'Q4')]:
            self.gates.append(Gate(label,plot.x,plot.y,[],plot.population,quadrant=[*point,hx,hy],quadrant_group=group))
        self.set_mode('select'); self.refresh()
    def delete_gate(self,gid):
        gate=next((g for g in self.gates if g.id==gid),None)
        if gate is None: return
        self.checkpoint()
        # A quadrant set is one gate to the user: deleting any quadrant removes all four.
        ids={g.id for g in self.gates if gate.quadrant_group and g.quadrant_group==gate.quadrant_group}|{gid}
        while any(g.parent in ids and g.id not in ids for g in self.gates): ids.update(g.id for g in self.gates if g.parent in ids)
        self.gates=[g for g in self.gates if g.id not in ids]
        for overlay in self.overlays:
            if overlay.get('population') in ids: overlay['population']=None
        for plot in list(self.plots):
            if plot.population in ids: self.plots.remove(plot); self.grid.removeWidget(plot); plot.deleteLater()
        self.active=self.plots[0] if self.plots else None; self.layout_plots(); self.refresh()
    def open_gate(self,gid):
        if not self.active: return
        self.checkpoint()
        x,y=self.active.x,self.active.y; names=[p.name for p in self.sample().parameters]
        if (x,y)==('FSC-A','SSC-A') and 'FSC-H' in names: y='FSC-H'
        elif (x,y)==('FSC-A','FSC-H'):
            fl=next((n for n in ('FL1-A','FL-1-A','FL1','FL-1') if n in names),None)
            if fl and 'SSC-A' in names: x,y=fl,'SSC-A'
        self.new_plot(gid,x,y); self.refresh()
    def refresh_table(self):
        s=self.sample(); p=self.active
        self.table.setRowCount(0); self.gate_percentages={}
        if not s or not p or not p.axes(): return
        ids=[None]+[g.id for g in self.gates]
        for gid in ids:
            g=next((g for g in self.gates if g.id==gid),None); sx=self.stats_cache.get(s,self.gates,gid,p.x)
            if gid is not None: self.gate_percentages[gid]=sx['percent_parent']
            depth=0; parent=g.parent if g else None; seen=set()
            while parent and parent not in seen:
                seen.add(parent); depth+=1; ancestor=next((a for a in self.gates if a.id==parent),None); parent=ancestor.parent if ancestor else None
            name=g.name if g else 'All Events'
            values=[name,fmt(sx['count']),fmt(sx['percent_parent']),fmt(sx['percent_total'])]
            row=self.table.rowCount(); self.table.insertRow(row)
            for col,value in enumerate(values):
                item=QTableWidgetItem(value); item.setData(Qt.ItemDataRole.UserRole,gid); item.setToolTip(value)
                if col==0 and g:
                    item.setData(Qt.ItemDataRole.UserRole+1,depth+1)
                    marker=g.color or ('#dddddd' if self.dark else '#292929'); item.setData(Qt.ItemDataRole.UserRole+2,marker)
                if col: item.setTextAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row,col,item)
            self.table.setRowHeight(row,26)
    def hierarchy_menu(self,pos):
        item=self.table.itemAt(pos); gid=item.data(Qt.ItemDataRole.UserRole) if item else None
        if gid is None: return
        self.table.selectRow(item.row()); menu=QMenu(self.table)
        menu.addAction('Edit…',lambda:self.edit_gate(gid)); menu.addAction('Delete gate',lambda:self.delete_gate(gid))
        menu.exec(self.table.viewport().mapToGlobal(pos))
    def delete_selected_row(self):
        item=self.table.currentItem(); gid=item.data(Qt.ItemDataRole.UserRole) if item else None
        if gid is not None: self.delete_gate(gid)
    def edit_row(self,row,col):
        gid=self.table.item(row,0).data(Qt.ItemDataRole.UserRole); self.edit_gate(gid)
    def edit_gate(self,gid):
        gate=next((g for g in self.gates if g.id==gid),None)
        if not gate: return
        dialog=GateDialog(self,gate.name,gate.color)
        if dialog.exec() and dialog.name.text().strip(): self.checkpoint(); gate.name=dialog.name.text().strip(); gate.color=dialog.color; self.refresh()
    def comparison_rows(self):
        parameter=self.parameter.currentData() or ''; gid=self.pop.currentData()
        field={'Median':'median','Mean':'mean','% of parent':'percent_parent'}[self.metric_combo.currentText()]
        key=(tuple((id(s),id(s.events),s.path,s.condition,tuple(p.name for p in s.parameters),population_signature(self.gates_for(s),gid)) for s in self.samples),parameter,field)
        if key==self._comparison_key and len(self._comparison_refs)==len(self.samples) and all(ref() is sample and events() is sample.events for (ref,events),sample in zip(self._comparison_refs,self.samples)):
            return self._comparison_rows
        self._comparison_key=key; self._comparison_refs=tuple((weakref.ref(s),weakref.ref(s.events)) for s in self.samples)
        self._comparison_rows=[(s.name,s.condition,self.stats_cache.get(s,self.gates_for(s),gid,parameter)[field]) for s in self.samples]
        return self._comparison_rows
    def comparison_changed(self,*args):
        if not self._loading and self._comparison_last is not None:
            current=(self.pop.currentData(),self.metric_combo.currentText(),self.parameter.currentData())
            if current!=self._comparison_last:
                self.checkpoint(); old=self._comparison_last
                self.history[-1]['population'],self.history[-1]['metric'],self.history[-1]['parameter']=old
        self.refresh_comparison()
    def update_event_warning(self):
        """Flag samples whose analysed population has fewer than LOW_EVENTS events."""
        gid=self.pop.currentData(); parameter=self.parameter.currentData() or ''; low=set()
        for sample in self.samples:
            count=self.stats_cache.get(sample,self.gates_for(sample),gid,parameter)['count']
            if count is not None and count<LOW_EVENTS: low.add(id(sample))
        self.low_event_samples=low; name=self.population_name(gid)
        self.event_warning.setText(f'● {len(low)} sample{"s" if len(low)!=1 else ""} with fewer than {LOW_EVENTS:,} events in {name}'); self.event_warning.setVisible(bool(low))
        for i in range(self.sample_list.count()):
            item=self.sample_list.item(i); sample=item.data(Qt.ItemDataRole.UserRole)
            item.setToolTip(sample.name+(f'\nFewer than {LOW_EVENTS:,} events in {name}' if id(sample) in low else ''))
        self.sample_list.viewport().update()
    def refresh_comparison(self,*args):
        self.update_event_warning()
        self._comparison_last=(self.pop.currentData(),self.metric_combo.currentText(),self.parameter.currentData())
        self.chart.update(); self.dirty()
    def analysis_table(self,layout):
        """Rows for the analysis plot in its condition order: 'long' has one row per sample,
        'wide' one column per condition (ready to paste into a Prism column table)."""
        metric=self.metric_combo.currentText(); gid=self.pop.currentData(); parameter=self.parameter.currentData() or ''
        population=self.pop.currentText() or 'All Events'; groups=self.chart.groups()
        values={}
        for sample,(name,condition,value) in zip(self.samples,self.comparison_rows()): values.setdefault(condition,[]).append((sample,value))
        if layout=='wide':
            columns=[[('' if value is None else value) for _,value in values.get(group,[])] for group in groups]
            depth=max((len(column) for column in columns),default=0)
            return [groups]+[[column[i] if i<len(column) else '' for column in columns] for i in range(depth)]
        rows=[['Sample','Condition','Population','Metric','Parameter','Value','Population count','Parent count']]
        for group in groups:
            for sample,value in values.get(group,[]):
                stats=self.stats_cache.get(sample,self.gates_for(sample),gid,parameter)
                rows.append([sample.name,group,population,metric,'' if metric=='% of parent' else parameter,'' if value is None else value,'' if stats['count'] is None else stats['count'],'' if stats['parent'] is None else stats['parent']])
        return rows
    def comparison_csv(self,delimiter=',',layout='long'): return export_csv(self.analysis_table(layout),delimiter)
    def export_name(self,layout):
        metric=self.metric_combo.currentText(); parameter=self.parameter.currentData() or ''
        measure='percent-of-parent' if metric=='% of parent' else parameter+('-mean' if metric=='Mean' else '')
        clean=lambda text:re.sub(r'[^A-Za-z0-9.+-]+','-',text).strip('-') or 'all'
        return f'{datetime.date.today():%Y-%m-%d}_{clean(measure)}_{clean(self.pop.currentText() or "All Events")}_{layout}.csv'
    def export_menu(self):
        menu=QMenu(self.export_button)
        menu.addAction('Save long CSV…',lambda:self.export_csv('long')); menu.addAction('Copy long table',lambda:self.copy_csv('long')); menu.addSeparator()
        menu.addAction('Save Prism CSV…',lambda:self.export_csv('wide')); menu.addAction('Copy Prism table',lambda:self.copy_csv('wide'))
        menu.exec(self.export_button.mapToGlobal(QPoint(0,self.export_button.height()+2)))
    def export_csv(self,layout='long'):
        name=self.export_name(layout)
        if self.project_path:
            # Saved projects: write next to the project without asking, never overwriting.
            path=Path(self.project_path).parent/name; number=2
            while path.exists(): path=path.with_name(f'{Path(name).stem}_{number}.csv'); number+=1
        else:
            chosen,_=remembered(QFileDialog.getSaveFileName(self,'Export data',str(Path(start_folder())/name),'CSV (*.csv)'))
            if not chosen: return None
            path=Path(chosen)
        try: path.write_text(self.comparison_csv(layout=layout),encoding='utf8',newline='')
        except OSError as exc: QMessageBox.warning(self,'Could not export',str(exc)); return None
        self.show_export_note('Saved',f'Saved {path}'); return path
    def copy_csv(self,layout='long'):
        QApplication.clipboard().setText(self.comparison_csv('\t',layout)); self.show_export_note('Copied','Copied the Prism table to the clipboard' if layout=='wide' else 'Copied the long table to the clipboard')
    def show_export_note(self,short,detail=''):
        """Brief confirmation in the header ('✓ Saved'); the full detail is in the tooltip."""
        self.export_note.setText('✓ '+short); self.export_note.setToolTip(detail or short); self.export_note_timer.start()
    def export_plot(self):
        if self.current_overlay: self.overlay_view.export_plot(); return
        if not self.active: return
        path,_=remembered(QFileDialog.getSaveFileName(self,'Export plot',start_folder(),'PNG (*.png)'))
        if path: self.active.grab().save(path,'PNG')
    def copy_plot(self,plot):
        if self.current_overlay: self.overlay_view.copy_plot()
        elif plot: QApplication.clipboard().setPixmap(plot.grab())
    def export_worksheet(self):
        path,_=remembered(QFileDialog.getSaveFileName(self,'Export worksheet',start_folder(),'PDF (*.pdf)'))
        if not path: return
        self.write_worksheet(path)
    def write_worksheet(self,path):
        writer=QPdfWriter(path); writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4)); painter=QPainter(writer)
        if not painter.isActive(): QMessageBox.warning(self,'Export failed','Could not write the PDF.'); return
        if self.current_overlay:
            graph=self.overlay_view.graph; scale=min(writer.width()/max(1,graph.width()),writer.height()/max(1,graph.height()))
            graph.exporting=True
            try: painter.scale(scale,scale); graph.render(painter,QPoint(0,0)); painter.end()
            finally: graph.exporting=False
            return
        scale=min(writer.width()/max(1,self.canvas.width()),writer.height()/max(1,self.canvas.height()+self.table.height()))
        painter.scale(scale,scale); self.canvas.render(painter,QPoint(0,0)); self.table.render(painter,QPoint(0,self.canvas.height())); painter.end()
    def relink_missing(self):
        if not self.missing:
            QMessageBox.information(self,'Relink files','No missing files.'); return
        remaining=[]; errors=[]
        for entry in self.missing:
            path,_=remembered(QFileDialog.getOpenFileName(self,'Locate '+Path(entry['path']).name,start_folder(),'FCS files (*.fcs *.FCS)'))
            if not path: remaining.append(entry); continue
            try:
                sample=read_fcs(path)
                if entry.get('checksum') and sample.checksum!=entry['checksum']: raise ValueError('The selected file does not match the original file.')
                sample.condition=entry.get('condition','Unassigned'); (self.controls if entry.get('control') else self.samples).append(sample)
                for overlay in self.overlays:
                    for item in overlay['entries']:
                        if item['path']==entry['path']: item['path']=sample.path
                if entry['path'] in self.sample_gates: self.sample_gates[sample.path]=self.sample_gates.pop(entry['path'])
            except (OSError,ValueError) as exc: remaining.append(entry); errors.append(str(exc))
        self.missing=remaining; self.samples.sort(key=lambda s:natural_key(s.name)); self.refresh()
        if errors: QMessageBox.warning(self,'Could not relink files','\n'.join(errors))
    def snapshot(self):
        return {'format':'cytose','version':1,'samples':[{'path':s.path,'condition':s.condition,'checksum':s.checksum} for s in self.samples]+[{'path':s.path,'condition':s.condition,'checksum':s.checksum,'control':True,'stain':self.control_stains.get(s.path)} for s in self.controls]+self.missing,'compensation':self.compensation,'gates':[asdict(g) for g in self.main_gates],'sample_gates':{path:[asdict(g) for g in gates] for path,gates in self.sample_gates.items()}, 'plots':[{'population':p.population,'x':p.x,'y':p.y,'bounds':p.bounds,'slot':p.grid_slot} for p in self.plots], 'selected':self.sample_list.currentRow(),'active_plot':self.plots.index(self.active) if self.active in self.plots else 0,'plot_columns':self.plot_columns,'dark':self.dark,'backgating':self.backgating,'annotations':self.annotations,'conditions':self.conditions,'condition_order':self.condition_order,'metric':self.metric_combo.currentText(),'parameter':self.parameter.currentData(),'population_id':self.pop.currentData(),'population':self.pop.currentIndex(),'overlays':self.overlays,'current_overlay':self.current_overlay}
    def dirty(self):
        if self.project_path and not self._loading:
            self.set_save_status('saving'); self.timer.start()
    def autosave(self):
        self.set_save_status('saving')
        try: save_json(self.project_path,self.snapshot())
        except (OSError,ValueError) as exc:
            self.set_save_status('error'); QMessageBox.warning(self,'Could not save project',str(exc)); return False
        self.set_save_status('saved'); return True
    def save_project(self,save_as=False):
        if save_as or not self.project_path:
            path,_=remembered(QFileDialog.getSaveFileName(self,'Save project',new_project_name(),'Cytose project (*.cytose)'))
            if not path: return False
            self.project_path=path if path.lower().endswith('.cytose') else path+'.cytose'
        self.timer.stop(); saved=self.autosave()
        if saved: self.update_tab_title()
        return saved
    def load_project(self,path):
        doc=json.loads(Path(path).read_text(encoding='utf8'))
        if doc.get('format')!='cytose' or doc.get('version')!=1: raise ValueError('Unsupported project format')
        samples=[]; missing=[]; controls=[]; stains={}
        for entry in doc['samples']:
            try:
                sample=read_fcs(entry['path'])
                if entry.get('checksum') and entry['checksum'] != sample.checksum: raise ValueError('Source file has changed')
                sample.condition=entry.get('condition','Unassigned'); (controls if entry.get('control') else samples).append(sample)
                if entry.get('control') and entry.get('stain'): stains[sample.path]=entry['stain']
            except (OSError,ValueError): missing.append(entry)
        gates=[Gate(**entry) for entry in doc['gates']]; sample_gates={path:[Gate(**entry) for entry in entries] for path,entries in doc.get('sample_gates',{}).items()}
        overlays=[o for o in doc.get('overlays',[]) if isinstance(o,dict) and o.get('id') and isinstance(o.get('entries'),list)]
        samples.sort(key=lambda s:natural_key(s.name)); self._loading=True; self.samples=samples; self.controls=controls; self.control_stains=stains; self.compensation=doc.get('compensation',{'enabled':False,'channels':[],'matrix':[]}); self.apply_compensation(); self.missing=missing; self.main_gates=gates; self.sample_gates=sample_gates; self.project_path=str(path); self.plot_columns=max(1,min(5,int(doc.get('plot_columns',3)))); self.dark=doc.get('dark',True); self.apply_theme(); self.annotations=doc.get('annotations',{}); self.conditions=doc.get('conditions',[]); self.condition_order=doc.get('condition_order',[]); self.backgate.setChecked(doc.get('backgating',False)); self.overlays=overlays
        for p in self.plots: self.grid.removeWidget(p); p.deleteLater()
        self.plots=[]
        for plot in doc.get('plots',[]): self.new_plot(plot['population'],plot['x'],plot['y'],plot['bounds'],plot.get('slot'))
        if not self.plots: self.new_plot(None)
        self.active=self.plots[min(max(0,doc.get('active_plot',0)),len(self.plots)-1)]
        self.refresh(); self.sample_list.setCurrentRow(min(doc.get('selected',0),len(samples)-1)); self.metric_combo.setCurrentText(doc.get('metric','Median')); self.parameter.setCurrentIndex(max(0,self.parameter.findData(doc.get('parameter',''))))
        if 'population_id' in doc: self.pop.setCurrentIndex(max(0,self.pop.findData(doc['population_id'])))
        else: self.pop.setCurrentIndex(doc.get('population',0))
        self.chart.switch_position=0. if self.metric_combo.currentText()=='% of parent' else 1.; self.chart.update(); self.restore_overlay(doc.get('current_overlay'))
        self._loading=False; self.set_save_status('saved')
        self.show_workspace()
        if missing: QMessageBox.warning(self,'Missing, changed or unreadable files','\n'.join(e['path'] for e in missing))


def fmt(value):
    if value is None: return '—'
    return f'{value:.4g}' if isinstance(value,(float,np.floating)) else str(value)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setObjectName('mainWindow'); self.setWindowTitle('Cytose')
        screen=QApplication.primaryScreen(); available=screen.availableGeometry() if screen else None
        self.resize(min(1700,available.width()) if available else 1700,min(950,available.height()) if available else 950)
        self.tabs=QTabWidget(); self.tabs.setObjectName('projectTabs'); self.tabs.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True); self.tabs.setTabBar(WorkspaceTabBar()); self.tabs.setDocumentMode(True); self.tabs.tabBar().tabCloseRequested.connect(self.close_tab); self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self.apply_current_theme)
        self.add_tab_button=TabIconButton('add'); self.add_tab_button.setParent(self.tabs.tabBar()); self.tabs.tabBar().add_button=self.add_tab_button
        self.add_tab_button.clicked.connect(self.new_tab); self.add_tab_button.show(); self.tabs.tabBar().tabMoved.connect(lambda *_:self.tabs.tabBar().position_add_button())
        menu=self.menuBar().addMenu('File'); menu.addAction('New quick analysis',self.new_tab,'Ctrl+T'); menu.addAction('Open project',self.open_project)
        help_menu=self.menuBar().addMenu('Help'); help_menu.addAction('Licenses',self.show_licenses)
        next_tab=QShortcut(QKeySequence('Ctrl+Tab'),self); next_tab.activated.connect(lambda:self.step_tab(1))
        previous_tab=QShortcut(QKeySequence('Ctrl+Shift+Tab'),self); previous_tab.activated.connect(lambda:self.step_tab(-1))
        self.new_tab()
    def apply_current_theme(self,*args):
        workspace=self.tabs.currentWidget()
        dark=workspace is None or workspace.dark
        QApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
        self.setStyleSheet(STYLE if dark else LIGHT_STYLE)
        self.tabs.tabBar().update()
        if hasattr(self,'add_tab_button'): self.add_tab_button.update()
    def show_licenses(self):
        if getattr(sys,'frozen',False):
            base=Path(sys.executable).parent
            legal=base.parent/'Resources'/'Legal' if sys.platform=='darwin' else base/'Legal'
        else: legal=Path(__file__).resolve().parents[1]/'licenses'
        QMessageBox.information(self,'Licenses',
            'Cytose is licensed under MIT. Cytose includes Qt and PySide6 under LGPL version 3, NumPy, Python and the Comfortaa font under their respective licenses.\n\n'
            'License texts, version information and source references for a packaged build are in:\n'+str(legal))
    def step_tab(self,delta):
        if self.tabs.count(): self.tabs.setCurrentIndex((self.tabs.currentIndex()+delta)%self.tabs.count())
    def new_tab(self):
        ws=Workspace(); i=self.tabs.addTab(ws,'(unsaved)'); self.tabs.setCurrentIndex(i); ws.update_tab_title()
    def open_condition(self,source,condition):
        ws=Workspace(); ws.samples=[copy.copy(sample) for sample in source.samples if sample.condition==condition]; ws.main_gates=copy.deepcopy(source.main_gates); ws.sample_gates={path:copy.deepcopy(gates) for path,gates in source.sample_gates.items() if any(s.path==path for s in ws.samples)}; ws.annotations=source.annotations.copy(); ws.conditions=source.conditions[:]; ws.condition_order=source.condition_order[:]; ws.dark=source.dark; ws.apply_theme(); ws.backgate.setChecked(source.backgating)
        paths={sample.path for sample in ws.samples}
        for overlay in copy.deepcopy(source.overlays):
            overlay['entries']=[entry for entry in overlay['entries'] if entry['path'] in paths]
            if overlay['entries']: ws.overlays.append(overlay)
        for plot in ws.plots: ws.grid.removeWidget(plot); plot.deleteLater()
        ws.plots=[]
        for plot in source.plots: ws.new_plot(plot.population,plot.x,plot.y,copy.deepcopy(plot.bounds))
        if source.active in source.plots: ws.active=ws.plots[source.plots.index(source.active)]
        ws.refresh(); ws.show_workspace(); self.tabs.setCurrentIndex(self.tabs.addTab(ws,'(unsaved)')); ws.update_tab_title()
    def confirm_close(self,ws):
        if ws.project_path:
            ws.timer.stop(); return ws.autosave()
        if not ws.samples and not ws.gates: return True
        choice=QMessageBox.question(self,'Unsaved analysis','Save this analysis before closing?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Save)
        if choice==QMessageBox.StandardButton.Cancel: return False
        if choice==QMessageBox.StandardButton.Save: return bool(ws.save_project())
        return choice==QMessageBox.StandardButton.Discard
    def close_tab(self,index):
        ws=self.tabs.widget(index)
        if not self.confirm_close(ws): return
        self.tabs.removeTab(index); ws.deleteLater()
        if not self.tabs.count(): self.new_tab()
    def open_project(self):
        path,_=remembered(QFileDialog.getOpenFileName(self,'Open project',start_folder(),'Cytose project (*.cytose)'))
        if not path: return
        ws=Workspace()
        try: ws.load_project(path)
        except (OSError,ValueError,KeyError,TypeError) as exc: QMessageBox.warning(self,'Could not open project',str(exc)); ws.deleteLater(); return
        self.tabs.setCurrentIndex(self.tabs.addTab(ws,Path(path).stem)); ws.update_tab_title()
    def closeEvent(self,event):
        for i in range(self.tabs.count()):
            ws=self.tabs.widget(i)
            if not self.confirm_close(ws): event.ignore(); return
        super().closeEvent(event)


def configure_font(app):
    font_dir=Path(__file__).parent/'fonts'
    families=[]
    for filename in ('Comfortaa-Regular.ttf','Comfortaa-Bold.ttf'):
        path=font_dir/filename
        if not path.is_file(): return False
        font_id=QFontDatabase.addApplicationFontFromData(QByteArray(path.read_bytes()))
        registered=QFontDatabase.applicationFontFamilies(font_id)
        if not registered: return False
        families.append(registered[0])
    if families[0]!=families[1]: return False
    app.setFont(QFont(families[0],10))
    return True


def main():
    app=QApplication(sys.argv); app.setApplicationName('Cytose'); configure_font(app)
    app.setStyleSheet(STYLE); window=MainWindow(); window.show(); return app.exec()
