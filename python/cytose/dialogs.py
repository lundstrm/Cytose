"""Shared pieces that give every popup the same footer and controls."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, QStandardPaths, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QStyledItemDelegate, QVBoxLayout


def add_done(dialog, layout, default=True):
    """Bottom-right Done button; Enter confirms when it is the default, Esc closes without changes."""
    row=QHBoxLayout(); row.setContentsMargins(0,0,0,0); row.addStretch()
    done=QPushButton('Done'); done.setObjectName('dialogDone'); done.setFixedHeight(30); done.setMinimumWidth(88)
    done.setDefault(default); done.setAutoDefault(default); done.clicked.connect(dialog.accept); row.addWidget(done)
    layout.addSpacing(4); layout.addLayout(row); return done


def ask_name(parent, title, name):
    """Small rename dialog matching the other popups; returns the stripped name or None."""
    dialog=QDialog(parent); dialog.setWindowTitle(title); layout=QVBoxLayout(dialog); layout.setContentsMargins(18,16,18,14); layout.setSpacing(6)
    layout.addWidget(QLabel('Name')); field=QLineEdit(name); field.selectAll(); layout.addWidget(field); add_done(dialog,layout); dialog.setMinimumWidth(320)
    accepted=dialog.exec()
    return (field.text().strip() or None) if accepted else None


class ChoiceCombo(QComboBox):
    """Combo box with the app's chevron in place of the platform arrow and a padded popup list."""
    def __init__(self,*args):
        super().__init__(*args); self.setItemDelegate(QStyledItemDelegate(self))
    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=QColor(self.palette().color(self.foregroundRole())); color.setAlpha(170); painter.setPen(QPen(color,1.3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        x,y=self.width()-14,self.height()/2
        painter.drawLine(QPointF(x-3,y-2),QPointF(x,y-5)); painter.drawLine(QPointF(x,y-5),QPointF(x+3,y-2))
        painter.drawLine(QPointF(x-3,y+2),QPointF(x,y+5)); painter.drawLine(QPointF(x,y+5),QPointF(x+3,y+2)); painter.end()


def _settings_file():
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))/'settings.json'


def start_folder():
    """Last folder used in a file dialog, else the Desktop (or home). An empty start folder
    would open the current working directory, which can be a slow cloud-synced folder."""
    try: folder=json.loads(_settings_file().read_text(encoding='utf8')).get('last_folder','')
    except (OSError,ValueError,AttributeError): folder=''
    if folder and Path(folder).is_dir(): return folder
    desktop=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    return desktop if desktop and Path(desktop).is_dir() else str(Path.home())


def new_project_name():
    """Suggested path for a new project: today's date as a prefix, ready for a name."""
    return str(Path(start_folder())/f'{date.today():%Y-%m-%d}_')


def remembered(result):
    """Pass a QFileDialog result through, storing its folder for the next dialog."""
    chosen=result[0]; chosen=chosen[0] if isinstance(chosen,list) and chosen else chosen
    if chosen:
        try:
            path=_settings_file(); path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'last_folder':str(Path(chosen).parent)}),encoding='utf8')
        except OSError: pass
    return result
