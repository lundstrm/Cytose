import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import numpy as np
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from PySide6.QtCore import QPoint, QPointF, QRectF, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontInfo, QFontMetricsF, QImage
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox, QPushButton, QSplitter, QTabBar, QWidget
from cytose.app import GateDialog, Workspace, MainWindow, Conditions, STYLE, WelcomeChoice, configure_font
from cytose.core import Parameter, Sample, statistics
from cytose.overlay import sample_mime
from cytose.plot import DARK_WORKSHEET_BACKGROUND, LIGHT_WORKSHEET_BACKGROUND, axis_ticks, log_scale, log_tick_label, positioned_tick_labels, tick_font, title_layout
from test_core import fixture, multichannel_fixture


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        QStandardPaths.setTestModeEnabled(True)  # keep remembered folders out of the user's real settings
    def test_bundled_fonts_apply_to_widgets_and_plot(self):
        old_font=self.app.font(); old_style=self.app.styleSheet()
        try:
            self.assertTrue(configure_font(self.app)); self.app.setStyleSheet(STYLE)
            self.assertIn('Regular',QFontDatabase.styles('Comfortaa'))
            self.assertIn('Bold',QFontDatabase.styles('Comfortaa'))
            ws=Workspace(); dialog=Conditions(ws); ws.show(); dialog.show(); self.app.processEvents()
            widgets=[ws,ws.active,ws.chart,ws.table,ws.pop,ws.tool_buttons['select'],dialog]
            widgets.extend(dialog.findChildren(QWidget))
            for widget in widgets:
                self.assertEqual(QFontInfo(widget.font()).family(),'Comfortaa',type(widget).__name__)
            dialog.close(); ws.close()
        finally:
            self.app.setStyleSheet(old_style); self.app.setFont(old_font)
    def test_import_gate_compare_and_reopen(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'A01 sample.fcs'; fixture(source)
            workspace=Workspace(); workspace.import_paths([str(source)]); workspace.show(); self.app.processEvents()
            plot=workspace.active; plot.axes(); plot.reset()
            workspace.add_gate(plot,[[0,0],[4,0],[4,5],[0,5]])
            self.assertEqual(workspace.comparison_rows()[0][2],3)
            workspace.open_gate(workspace.gates[0].id); self.assertEqual(len(workspace.plots),2)
            workspace.annotations={'FSC-A':'Marker'}; workspace.conditions=['Empty']; workspace.condition_order=['Example']; workspace.refresh()
            workspace.pop.setCurrentIndex(1); workspace.metric_combo.setCurrentText('Mean')
            workspace.backgate.setChecked(True); self.app.processEvents(); self.assertFalse(plot.grab().isNull())
            pdf=Path(d)/'worksheet.pdf'
            with patch('cytose.app.QFileDialog.getSaveFileName',return_value=(str(pdf),'PDF')):
                workspace.export_worksheet()
            self.assertTrue(pdf.read_bytes().startswith(b'%PDF'))
            project=Path(d)/'test.cytose'; workspace.project_path=str(project); workspace.autosave()
            restored=Workspace(); restored.load_project(project); self.app.processEvents()
            self.assertEqual(len(restored.gates),1); self.assertEqual(len(restored.plots),2); self.assertEqual(restored.samples[0].events.shape,(3,2))
            self.assertTrue(restored.backgating)
            self.assertEqual(restored.conditions,['Empty'])
            self.assertEqual(restored.annotations,{'FSC-A':'Marker'}); self.assertEqual(restored.condition_order,['Example'])
            self.assertEqual(restored.pop.currentData(),workspace.gates[0].id); self.assertEqual(restored.metric_combo.currentText(),'Mean')
            self.assertEqual(restored.active.population,workspace.gates[0].id)
            workspace.timer.stop(); restored.timer.stop(); workspace.close(); restored.close()

    def test_condition_tab_is_independent(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'A01 sample.fcs'; fixture(source)
            window=MainWindow(); ws=window.tabs.currentWidget(); ws.import_paths([str(source)])
            ws.samples[0].condition='Control'; ws.add_gate(ws.active,[[0,0],[4,0],[4,5],[0,5]])
            window.open_condition(ws,'Control'); child=window.tabs.currentWidget()
            self.assertEqual(len(child.samples),1); self.assertEqual(len(child.gates),1)
            self.assertTrue(child.dark); self.assertIn(DARK_WORKSHEET_BACKGROUND,child.canvas.styleSheet())
            child.gates[0].name='Changed'; child.samples[0].condition='Other'
            self.assertNotEqual(ws.gates[0].name,child.gates[0].name); self.assertEqual(ws.samples[0].condition,'Control')
            with patch('cytose.app.QMessageBox.question',return_value=QMessageBox.StandardButton.Discard): window.close()

    def test_app_theme_follows_active_workspace(self):
        window=MainWindow(); window.show(); ws=window.tabs.currentWidget(); ws.show_workspace(); ws.toggle_theme(); self.app.processEvents()
        self.assertFalse(ws.dark); self.assertIn(LIGHT_WORKSHEET_BACKGROUND,window.styleSheet())
        self.assertEqual(ws.chart.grab().toImage().pixelColor(0,0),QColor(LIGHT_WORKSHEET_BACKGROUND))
        window.new_tab(); self.app.processEvents(); self.assertTrue(window.tabs.currentWidget().dark)
        self.assertIn(DARK_WORKSHEET_BACKGROUND,window.styleSheet())
        window.tabs.setCurrentWidget(ws); self.app.processEvents(); self.assertIn(LIGHT_WORKSHEET_BACKGROUND,window.styleSheet())
        with patch('cytose.app.QMessageBox.question',return_value=QMessageBox.StandardButton.Discard): window.close()

    def test_rectangle_interaction_and_delete(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.show_workspace(); ws.resize(1500,900); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); ws.set_mode('rectangle')
            start=plot.xy(1,2).toPoint(); end=plot.xy(4,5).toPoint()
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
            QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end)
            self.assertEqual(len(ws.gates),1)
            ws.set_mode('select'); QTest.mouseClick(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,plot.xy(2,3).toPoint())
            self.assertEqual(plot.selected,ws.gates[0].id)
            QTest.keyClick(plot,Qt.Key.Key_Delete); self.assertFalse(ws.gates)
            ws.close()

    def test_gate_deselects_when_clicking_elsewhere(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.resize(1500,900); ws.show_workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); ws.add_gate(plot,[[1,2],[4,2],[4,5],[1,5]])
            point=plot.xy(2,3).toPoint(); QTest.mouseClick(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
            self.assertEqual(plot.selected,ws.gates[0].id)
            QTest.mouseClick(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
            self.assertEqual(plot.selected,ws.gates[0].id)
            QTest.mouseClick(ws.sample_list.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(10,10))
            self.assertIsNone(plot.selected); self.assertIsNone(ws.selected_gate)
            QTest.mouseClick(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
            QTest.mouseClick(ws.scroll.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(ws.scroll.viewport().width()-5,ws.scroll.viewport().height()-5))
            self.assertIsNone(plot.selected); ws.close()

    def test_worksheet_empty_loaded_and_dark_layout(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.resize(1200,800); ws.show_workspace(); ws.show(); self.app.processEvents()
            self.assertTrue(ws.empty_label.isVisible()); self.assertFalse(ws.active.isVisible()); self.assertTrue(ws.card.isVisible()); self.assertEqual(ws.table.rowCount(),0)
            ws.import_paths([str(source)]); self.app.processEvents()
            self.assertFalse(ws.empty_label.isVisible()); self.assertTrue(ws.active.isVisible()); self.assertTrue(ws.card.isVisible())
            headers=[ws.table.horizontalHeaderItem(i).text() for i in range(ws.table.columnCount())]
            self.assertEqual(headers,['Population','Events','%\nparent','%\ntotal']); self.assertTrue(ws.backgate.isCheckable())
            for i in range(1,4): self.assertTrue(ws.table.horizontalHeaderItem(i).textAlignment() & Qt.AlignmentFlag.AlignRight)
            self.assertLessEqual(abs(ws.card.height()-ws.chart.parentWidget().height()),1)
            ws.add_gate(ws.active,[[0,0],[4,0],[4,5],[0,5]])
            self.assertEqual(ws.table.item(1,0).data(Qt.ItemDataRole.UserRole+2),'#dddddd')
            self.assertEqual(ws.table.item(1,0).data(Qt.ItemDataRole.UserRole+1),1)
            ws.gates[0].color='#c23537'; ws.refresh_table(); self.app.processEvents()
            item=ws.table.item(1,0); rect=ws.table.visualItemRect(item); image=ws.table.viewport().grab().toImage(); ratio=ws.table.viewport().devicePixelRatioF()
            self.assertEqual(image.pixelColor(round((rect.left()+2+11+3)*ratio),round(rect.center().y()*ratio)),QColor('#c23537'))
            with patch.object(ws,'edit_gate') as edit:
                ws.table.cellDoubleClicked.emit(1,1)
                edit.assert_called_once_with(ws.gates[0].id)
            self.assertEqual(ws.current_sample_label.text(),'sample.fcs')
            self.assertTrue(ws.dark); self.assertIn(DARK_WORKSHEET_BACKGROUND,ws.canvas.styleSheet())
            self.assertEqual(ws.active.grab().toImage().pixelColor(5,100),QColor(DARK_WORKSHEET_BACKGROUND))
            ws.toggle_theme(); self.assertFalse(ws.dark); self.assertIn(LIGHT_WORKSHEET_BACKGROUND,ws.canvas.styleSheet())
            self.app.processEvents()
            self.assertEqual(ws.active.grab().toImage().pixelColor(5,100),QColor(LIGHT_WORKSHEET_BACKGROUND))
            ws.close()

    def test_worksheet_toolbar_controls_and_shortcuts(self):
        ws=Workspace(); ws.resize(1500,800); ws.show_workspace(); ws.show(); self.app.processEvents()
        controls=list(ws.tool_buttons.values())+ws.toolbar_actions
        self.assertEqual(len({button.height() for button in controls}),1)
        self.assertTrue(all(button.isVisible() for button in controls))
        self.assertTrue(all(button.toolTip() for button in controls))
        QTest.mouseClick(ws.tool_buttons['polygon'],Qt.MouseButton.LeftButton)
        self.assertEqual(ws.mode,'polygon'); self.assertTrue(ws.tool_buttons['polygon'].isChecked())
        QTest.keyClick(ws,Qt.Key.Key_2); self.assertEqual(ws.mode,'zoom')
        QTest.keyClick(ws,Qt.Key.Key_B); self.assertTrue(ws.backgating); QTest.keyClick(ws,Qt.Key.Key_Equal); self.assertEqual(ws.plot_columns,2)
        QTest.keyClick(ws,Qt.Key.Key_Z); self.assertEqual(ws.plot_columns,3); QTest.keyClick(ws,Qt.Key.Key_X); self.assertEqual(ws.plot_columns,2)
        QTest.mouseClick(ws.toolbar_actions[-1],Qt.MouseButton.LeftButton); self.assertFalse(ws.dark)
        ws.close()

    def test_analysis_layout_and_bar_reordering_keep_sample_order(self):
        rows=[('A.fcs','Long treatment name',10.),('B.fcs','Control',20.),('C.fcs','Long treatment name',14.)]
        ws=Workspace()
        with patch.object(ws,'comparison_rows',return_value=rows):
            ws.resize(1500,900); ws.show_workspace(); ws.show(); ws.refresh_comparison(); self.app.processEvents()
            chart=ws.chart; groups=chart.groups(rows); rect,rotated,label_height=chart.plot_geometry(groups,chart.value_limits(rows,groups))
            self.assertTrue(rotated); self.assertGreater(label_height,18); self.assertGreater(rect.height(),80)
            start=QPoint(round(rect.left()+rect.width()*.25),round(rect.center().y()))
            end=QPoint(round(rect.left()+rect.width()*.75),round(rect.center().y()))
            QTest.mousePress(chart,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
            original=chart.drag_bar
            QTest.mouseMove(chart,end); preview=chart.drag_preview_rect()
            self.assertEqual(preview.size(),original.size()); self.assertAlmostEqual(preview.left()-original.left(),end.x()-start.x())
            self.assertEqual(chart.preview_order,['Control','Long treatment name']); self.assertTrue(chart.animation_timer.isActive())
            QTest.qWait(60); self.assertGreater(chart.positions['Long treatment name'],0)
            QTest.mouseRelease(chart,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end)
            self.assertEqual(ws.condition_order,['Control','Long treatment name'])
            self.assertEqual([row[0] for row in ws.comparison_rows()],['A.fcs','B.fcs','C.fcs'])
            self.assertFalse(chart.grab().isNull())
            chart.copy_plot(); copied=QApplication.clipboard().pixmap().toImage()
            self.assertEqual(copied.pixelColor(2,2),QColor('#ffffff')); self.assertFalse(chart.export_light)
        ws.close()

    def test_analysis_plot_controls_population_parameter_and_metric(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.resize(1500,900); ws.show_workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            ws.add_gate(ws.active,[[0,0],[4,0],[4,5],[0,5]])
            chart=ws.chart; self.app.processEvents()
            self.assertTrue(ws.pop.isHidden()); self.assertTrue(ws.parameter.isHidden()); self.assertFalse(hasattr(ws,'results'))
            def select_second_choice():
                menu=QApplication.activePopupWidget()
                QTest.mouseClick(menu,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,menu.actionGeometry(menu.actions()[1]).center())
            QTimer.singleShot(0,select_second_choice)
            QTest.mouseClick(chart,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,chart.title_rect().center().toPoint())
            self.assertEqual(ws.pop.currentData(),ws.gates[0].id)
            rows=ws.comparison_rows(); groups=chart.groups(rows); rect,_,_=chart.plot_geometry(groups,chart.value_limits(rows,groups))
            self.assertAlmostEqual(chart.title_rect(rect).center().x(),rect.center().x())
            QTimer.singleShot(0,select_second_choice)
            QTest.mouseClick(chart,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,chart.axis_title_rect(rect).center().toPoint())
            self.assertEqual(ws.parameter.currentData(),'SSC-A'); self.assertEqual(ws.comparison_rows()[0][2],3.)
            switch=chart.switch_rect(rect)
            QTest.mouseClick(chart,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(round(switch.center().x()),round(switch.bottom()-10)))
            self.assertEqual(ws.metric_combo.currentText(),'% of parent'); self.assertAlmostEqual(ws.comparison_rows()[0][2],200/3)
            row=ws.comparison_csv().splitlines()[1].split(','); self.assertEqual(row[3:5],['% of parent',''])
            with patch.object(chart,'open_choice') as picker:
                QTest.mouseClick(chart,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,chart.axis_title_rect(rect).center().toPoint()); picker.assert_not_called()
            QTest.mouseClick(chart,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(round(switch.center().x()),round(switch.top()+10)))
            self.assertEqual(ws.metric_combo.currentText(),'Median'); self.assertEqual(ws.comparison_rows()[0][2],3.)
            ws.close()

    def test_condition_filter_completion_assignment_and_rename(self):
        with tempfile.TemporaryDirectory() as d:
            files=[Path(d)/name for name in ('A01 A375.fcs','A02 A375.fcs','B01 HeLa.fcs')]
            for path in files: fixture(path)
            ws=Workspace(); ws.import_paths([str(path) for path in files]); dialog=Conditions(ws); dialog.show(); self.app.processEvents()
            dialog.search.setText('A37'); self.assertEqual(len(dialog.selected()),2); self.assertEqual(dialog.suggestion_text(),'A375')
            QTest.keyClick(dialog.search,Qt.Key.Key_Tab); self.assertEqual(dialog.search.text(),'A375'); self.assertEqual(dialog.condition.currentText(),'A375')
            dialog.assign(); self.assertEqual([s.condition for s in ws.samples],['A375','A375','Unassigned']); self.assertEqual(dialog.search.text(),'')
            self.assertIn('A375',ws.conditions); ws.condition_order=['A375']
            editor=dialog.conditions.itemWidget(dialog.conditions.item(0)).findChild(QLineEdit)
            editor.setReadOnly(False); editor.setText('Renamed'); dialog.rename('A375',editor)
            self.assertEqual(ws.samples[0].condition,'Renamed'); self.assertEqual(ws.condition_order,['Renamed'])
            dialog.remove('Renamed'); self.assertEqual(ws.samples[0].condition,'Unassigned')
            dialog.close(); ws.close()

    def test_condition_rows_fit_and_samples_are_sorted(self):
        with tempfile.TemporaryDirectory() as d:
            files=[Path(d)/name for name in ('B02 Zebra.fcs','A02 Alpha.fcs','A01 Alpha.fcs')]
            for path in files: fixture(path)
            ws=Workspace(); ws.import_paths([str(path) for path in files]); ws.conditions=['Zebra','Alpha']
            old_style=self.app.styleSheet(); self.app.setStyleSheet(STYLE)
            try:
                dialog=Conditions(ws); dialog.resize(820,520); dialog.show(); self.app.processEvents()
                self.assertEqual([dialog.list.item(i).data(Qt.ItemDataRole.UserRole).name for i in range(3)],['A01 Alpha.fcs','A02 Alpha.fcs','B02 Zebra.fcs'])
                names=[]
                for i in range(dialog.conditions.count()):
                    item=dialog.conditions.item(i); row=dialog.conditions.itemWidget(item); editor=row.findChild(QLineEdit)
                    names.append(editor.text())
                    self.assertGreaterEqual(dialog.conditions.visualItemRect(item).height(),row.sizeHint().height())
                    for child in [editor]+row.findChildren(QPushButton):
                        self.assertGreaterEqual(child.geometry().top(),0)
                        self.assertLessEqual(child.geometry().bottom(),row.height()-1)
                self.assertEqual(names,['Alpha','Zebra'])
                dialog.search.setText('Alpha'); self.assertEqual(len(dialog.selected()),2)
                QTest.keyClick(dialog.search,Qt.Key.Key_Return); self.assertTrue(dialog.isVisible())
                self.assertEqual(dialog.search.text(),''); self.assertEqual(sum(sample.condition=='Alpha' for sample in ws.samples),2)
                dialog.close()
            finally:
                self.app.setStyleSheet(old_style); ws.close()

    def test_condition_sample_row_selection_escape_and_clear_assignments(self):
        with tempfile.TemporaryDirectory() as d:
            paths=[Path(d)/name for name in ('A01 Alpha.fcs','A02 Alpha.fcs','B01 Beta.fcs')]
            for path in paths: fixture(path)
            ws=Workspace(); ws.import_paths([str(path) for path in paths]); ws.conditions=['Alpha','Beta']
            ws.condition_order=['Beta','Alpha']; ws.missing=[{'path':'missing.fcs','condition':'Alpha'}]
            for sample in ws.samples: sample.condition='Alpha' if 'Alpha' in sample.name else 'Beta'
            dialog=Conditions(ws); dialog.show(); self.app.processEvents()
            first=dialog.list.item(0); rect=dialog.list.visualItemRect(first)
            self.assertEqual(dialog.assign_button.text(),'Assign (0)')
            auto=next(button for button in dialog.findChildren(QPushButton) if button.text()=='Auto-Assign')
            clear=next(button for button in dialog.findChildren(QPushButton) if button.text()=='Clear')
            self.assertLess(auto.geometry().left(),clear.geometry().left())
            QTest.mouseClick(dialog.list.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(rect.right()-8,rect.center().y()))
            self.assertEqual(first.checkState(),Qt.CheckState.Checked); self.assertEqual(len(dialog.selected()),1); self.assertEqual(dialog.assign_button.text(),'Assign (1)')
            QTest.mouseClick(dialog.list.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(rect.left()+10,rect.center().y()))
            self.assertEqual(first.checkState(),Qt.CheckState.Unchecked)
            QTest.mouseClick(dialog.list.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(rect.center().x(),rect.center().y()))
            QTest.keyClick(dialog.search,Qt.Key.Key_Escape); self.assertTrue(dialog.isVisible()); self.assertFalse(dialog.selected())
            dialog.search.setText('Alpha'); self.assertEqual(len(dialog.selected()),2)
            QTest.keyClick(dialog.search,Qt.Key.Key_Escape); self.assertEqual(dialog.search.text(),''); self.assertFalse(dialog.selected())
            button=next(button for button in dialog.findChildren(QPushButton) if button.text()=='Clear')
            QTest.mouseClick(button,Qt.MouseButton.LeftButton); self.assertTrue(all(sample.condition=='Unassigned' for sample in ws.samples))
            self.assertEqual(ws.conditions,[]); self.assertEqual(ws.condition_order,[]); self.assertEqual(ws.missing[0]['condition'],'Unassigned'); self.assertEqual(dialog.conditions.count(),0)
            ws.undo(); self.assertEqual(ws.conditions,['Alpha','Beta']); self.assertEqual(ws.condition_order,['Beta','Alpha']); self.assertEqual(ws.missing[0]['condition'],'Alpha')
            self.assertEqual([sample.condition for sample in ws.samples],['Alpha','Alpha','Beta'])
            for sample in ws.samples: sample.condition='Unassigned'
            ws.missing=[]; dialog.refresh(); QTest.mouseClick(button,Qt.MouseButton.LeftButton)
            self.assertEqual(ws.conditions,[]); self.assertEqual(dialog.conditions.count(),0)
            dialog.close(); ws.close()

    def test_double_click_gate_and_clamp_zoom(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.resize(1100,700); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); original=[tuple(b) for b in plot.bounds]
            ws.add_gate(plot,[[1,2],[4,2],[4,5],[1,5]]); ws.set_mode('select')
            QTest.mouseDClick(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,plot.xy(2,3).toPoint())
            self.assertEqual(len(ws.plots),2); self.assertEqual(ws.active.population,ws.gates[0].id)
            ws.set_mode('zoom'); point=plot.xy(3,4).toPoint()
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
            QTest.mouseMove(plot,QPoint(plot.width()+200,-100)); self.assertIsNotNone(plot.drag_cursor)
            self.assertTrue(plot.plot_rect().contains(plot.drag_cursor))
            QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(plot.width()+200,-100))
            for previous,current in zip(original,plot.bounds):
                self.assertGreaterEqual(current[0],previous[0]); self.assertLessEqual(current[1],previous[1])
            ws.set_mode('polygon'); plot.draft=[]
            QTest.mouseClick(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,plot.plot_rect().center().toPoint())
            QTest.mouseMove(plot,plot.plot_rect().topLeft().toPoint()+QPoint(10,10)); self.assertIsNotNone(plot.cursor)
            ws.close()

    def test_new_tab_welcome_and_create_project(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source); project=Path(d)/'analysis.cytose'
            window=MainWindow(); ws=window.tabs.currentWidget(); self.assertIs(ws.pages.currentWidget(),ws.welcome_page)
            with patch('cytose.app.QFileDialog.getSaveFileName',return_value=(str(project.with_suffix('')),'Cytose')) as picker:
                ws.new_project(); self.assertIn('*.cytose',picker.call_args.args[-1])
            ws.timer.stop(); ws.autosave(); self.assertTrue(project.exists()); self.assertEqual(len(ws.samples),1)
            self.assertEqual(json.loads(project.read_text())['format'],'cytose')
            self.assertIs(ws.pages.currentWidget(),ws.workspace_page); self.assertEqual(window.tabs.tabText(0),'analysis')
            window.new_tab(); self.assertIs(window.tabs.currentWidget().pages.currentWidget(),window.tabs.currentWidget().welcome_page)
            with patch('cytose.app.QFileDialog.getOpenFileName',return_value=(str(project),'Cytose')): window.tabs.currentWidget().open_project_here()
            self.assertEqual(len(window.tabs.currentWidget().samples),1)
            window.close()

    def test_tab_save_indicator_tracks_pending_success_failure_and_reopen(self):
        with tempfile.TemporaryDirectory() as d:
            window=MainWindow(); window.show(); ws=window.tabs.currentWidget(); bar=window.tabs.tabBar()
            self.assertEqual(bar.tabData(0),'unsaved'); self.assertFalse(bar.spinner_timer.isActive())
            ws.project_path=str(Path(d)/'test.cytose'); self.assertTrue(ws.autosave()); ws.update_tab_title()
            self.assertEqual(bar.tabData(0),'saved'); self.assertIn('saved',bar.tabToolTip(0).lower())
            ws.dirty(); self.assertEqual(bar.tabData(0),'saving'); self.assertTrue(bar.spinner_timer.isActive())
            self.assertEqual(bar.spinner_timer.interval(),16)
            angle=bar.spinner_angle; QTest.qWait(40); self.assertNotEqual(bar.spinner_angle,angle)
            ws.timer.stop(); self.assertTrue(ws.autosave()); self.assertEqual(bar.tabData(0),'saved'); self.assertFalse(bar.spinner_timer.isActive())
            with patch('cytose.app.save_json',side_effect=OSError('disk error')), patch('cytose.app.QMessageBox.warning'):
                self.assertFalse(ws.autosave())
            self.assertEqual(bar.tabData(0),'error'); self.assertIn('could not',bar.tabToolTip(0))
            with patch('cytose.app.QFileDialog.getOpenFileName',return_value=(ws.project_path,'')):
                window.open_project()
            self.assertEqual(bar.tabData(1),'saved')
            window.close()

    def test_tab_controls_close_correct_tab_after_reordering(self):
        window=MainWindow(); window.show(); self.app.processEvents()
        tabs=window.tabs; first=tabs.currentWidget()
        self.assertEqual(tabs.tabText(0),'(unsaved)')
        QTest.mouseClick(window.add_tab_button,Qt.MouseButton.LeftButton)
        self.assertEqual(tabs.count(),2); second=tabs.currentWidget()
        self.assertEqual(tabs.tabText(1),'(unsaved)')
        tabs.tabBar().moveTab(0,1); self.app.processEvents()
        close=tabs.tabBar().tabButton(0,QTabBar.ButtonPosition.RightSide)
        QTest.mouseClick(close,Qt.MouseButton.LeftButton)
        self.assertEqual(tabs.count(),1); self.assertIs(tabs.currentWidget(),first)
        self.assertIsNot(tabs.currentWidget(),second)
        close=tabs.tabBar().tabButton(0,QTabBar.ButtonPosition.RightSide)
        QTest.mouseClick(close,Qt.MouseButton.LeftButton)
        self.assertEqual(tabs.count(),1); self.assertEqual(tabs.tabText(0),'(unsaved)')
        window.close()

    def test_new_tab_button_aligned_with_tabs(self):
        old_style=self.app.styleSheet()
        try:
            self.app.setStyleSheet(STYLE); window=MainWindow(); window.show(); self.app.processEvents()
            bar=window.tabs.tabBar()
            workspace=window.tabs.currentWidget(); margins=workspace.workspace_page.layout().contentsMargins()
            self.assertEqual((margins.left(),margins.top(),margins.right(),margins.bottom()),(7,7,7,7))
            self.assertEqual(workspace.workspace_page.findChild(QSplitter,'workspaceSplitter').handleWidth(),7)
            pill=bar.pill_rect(0); close=bar.tabButton(0,QTabBar.ButtonPosition.RightSide)
            self.assertLessEqual(abs(QRectF(window.add_tab_button.geometry()).center().y()-pill.center().y()),1)
            self.assertLessEqual(abs(QRectF(close.geometry()).center().y()-pill.center().y()),1); self.assertTrue(pill.contains(QRectF(close.geometry())))
            self.assertGreaterEqual(window.add_tab_button.x(),bar.tabRect(0).right())
            QTest.mouseClick(window.add_tab_button,Qt.MouseButton.LeftButton); self.app.processEvents()
            self.assertGreaterEqual(window.add_tab_button.x(),bar.tabRect(1).right())
            screenshot=window.grab(); image=screenshot.toImage(); ratio=screenshot.devicePixelRatioF()
            bar_top=bar.mapTo(window,QPoint(0,1)).y()
            self.assertEqual(image.pixelColor(round(2*ratio),round(bar_top*ratio)),image.pixelColor(round(200*ratio),round(bar_top*ratio)))
            window.close()
        finally:
            self.app.setStyleSheet(old_style)

    def test_double_click_quadrant_opens_population(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); ws.add_quadrants(plot,[3,4]); ws.set_mode('select')
            self.assertEqual([gate.name for gate in ws.gates],['Q1','Q2','Q3','Q4'])
            self.assertTrue(all(gate.color is None for gate in ws.gates))
            QTest.mouseDClick(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,plot.xy(4,5).toPoint())
            self.assertEqual(len(ws.plots),2); self.assertEqual(next(g.name for g in ws.gates if g.id==ws.active.population),'Q2')
            ws.close()

    def test_quadrant_handles_move_only_their_group_and_support_undo(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.resize(1500,900); ws.show_workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); ws.add_quadrants(plot,[3.,4.]); ws.add_quadrants(plot,[3.,4.])
            first=ws.gates[0]; group=first.quadrant_group; other=ws.gates[4].quadrant_group
            self.assertNotEqual(group,other); plot.selected=first.id; ws.selected_gate=first.id
            start=plot.xy(3.,4.).toPoint(); end=plot.xy(3.5,4.5).toPoint()
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
            QTest.mouseMove(plot,end)
            self.assertTrue(all(g.quadrant[:2]!=[3.,4.] for g in ws.gates if g.quadrant_group==group))
            QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end)
            self.assertEqual(len({tuple(g.quadrant[:2]) for g in ws.gates if g.quadrant_group==group}),1)
            self.assertTrue(all(g.quadrant[:2]==[3.,4.] for g in ws.gates if g.quadrant_group==other))
            old_x,old_y=ws.gates[0].quadrant[:2]
            endpoint=QPoint(round(plot.xy(old_x,old_y).x()),round(plot.plot_rect().top()))
            target=QPoint(round(plot.xy(4.,old_y).x()),endpoint.y())
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,endpoint)
            QTest.mouseMove(plot,target); QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,target)
            # An outer handle tilts only its own spoke; the centre and the other spokes stay put.
            gate=ws.gates[0]; self.assertEqual(gate.quadrant[:2],[old_x,old_y]); self.assertIsNotNone(gate.spokes)
            center,ends=plot.spoke_ends(gate); self.assertAlmostEqual(ends[0].x(),target.x(),delta=1); self.assertAlmostEqual(ends[2].x(),center.x(),delta=1)
            self.assertAlmostEqual(ends[1].y(),center.y(),delta=1); self.assertTrue(all(g.spokes==gate.spokes for g in ws.gates if g.quadrant_group==group))
            self.assertTrue(all(g.spokes is None for g in ws.gates if g.quadrant_group==other))
            ws.undo(); self.assertIsNone(ws.gates[0].spokes); self.assertEqual(ws.gates[0].quadrant[:2],[old_x,old_y])
            plot=ws.active; plot.selected=ws.gates[0].id; ws.selected_gate=plot.selected
            endpoint=QPoint(round(plot.plot_rect().right()),round(plot.xy(old_x,old_y).y()))
            target=QPoint(endpoint.x(),round(plot.xy(old_x,5.).y()))
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,endpoint)
            QTest.mouseMove(plot,target); QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,target)
            center,ends=plot.spoke_ends(ws.gates[0]); self.assertEqual(ws.gates[0].quadrant[:2],[old_x,old_y]); self.assertAlmostEqual(ends[1].y(),target.y(),delta=1); self.assertAlmostEqual(ends[3].y(),center.y(),delta=1)
            project=Path(d)/'quadrants.cytose'; ws.project_path=str(project); self.assertTrue(ws.autosave())
            restored=Workspace(); restored.load_project(project)
            self.assertEqual([g.quadrant_group for g in restored.gates],[g.quadrant_group for g in ws.gates])
            self.assertEqual([g.spokes for g in restored.gates],[g.spokes for g in ws.gates])
            ws.timer.stop(); restored.timer.stop(); restored.close()
            ws.close()

    def test_plot_close_control_only_appears_on_hover(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.resize(1500,900); ws.show_workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            ws.add_gate(ws.active,[[0,0],[4,0],[4,5],[0,5]]); ws.open_gate(ws.gates[0].id)
            plot=ws.active; self.app.processEvents()
            with patch.object(plot,'underMouse',return_value=False): hidden=plot.grab().toImage()
            with patch.object(plot,'underMouse',return_value=True): shown=plot.grab().toImage()
            ratio=plot.devicePixelRatioF(); left=round((plot.width()-27*ws.plot_zoom)*ratio); top=round(25*ws.plot_zoom*ratio)
            self.assertTrue(any(hidden.pixelColor(x,y)!=shown.pixelColor(x,y) for x in range(max(0,left),hidden.width()) for y in range(min(top,hidden.height()))))
            with patch.object(plot,'underMouse',return_value=True): QTest.mouseClick(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(plot.width()-round(12*ws.plot_zoom),round(10*ws.plot_zoom)))
            self.assertNotIn(plot,ws.plots); ws.close()

    def test_worksheet_plot_reordering_and_size_persist(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.resize(1700,900); ws.import_paths([str(source)]); ws.show_workspace(); ws.show(); self.app.processEvents()
            ws.add_gate(ws.active,[[0,0],[4,0],[4,5],[0,5]])
            ws.new_plot(ws.gates[0].id); self.app.processEvents()
            first,second=ws.plots; old_width=first.width(); old_font=first.font().pointSizeF()
            self.assertEqual(ws.plot_columns,3)
            ws.set_plot_columns(2); self.app.processEvents(); self.assertGreater(first.width(),old_width)
            if old_font>0: self.assertAlmostEqual(first.font().pointSizeF()/old_font,first.width()/old_width,places=1)
            with patch.object(ws,'move_plot',wraps=ws.move_plot) as move:
                QTest.mousePress(first,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(80,10))
                target=first.mapFromGlobal(second.mapToGlobal(QPoint(80,10)))
                QTest.mouseMove(first,target)
                self.assertTrue(ws.plot_preview.isVisible()); self.assertIsNotNone(ws.plot_preview.image); self.assertIsNotNone(ws.plot_preview.destination)
                QTest.mouseRelease(first,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,target)
                self.assertFalse(ws.plot_preview.isVisible())
                move.assert_called_once()
            self.assertEqual((first.grid_slot,second.grid_slot),(1,0))
            empty=ws.scroll.viewport().mapToGlobal(QPoint(20,first.height()+35))
            ws.move_plot(second,empty); self.app.processEvents()
            self.assertGreater(second.grid_slot,1)
            empty_slot=second.grid_slot
            project=Path(d)/'layout.cytose'; ws.project_path=str(project); self.assertTrue(ws.autosave())
            restored=Workspace(); restored.load_project(project); self.assertEqual(restored.plot_columns,2)
            self.assertEqual(restored.plots[1].grid_slot,empty_slot)
            ws.undo(); self.assertEqual(ws.plots[1].grid_slot,0)
            ws.timer.stop(); restored.timer.stop(); ws.close(); restored.close()

    def test_plot_columns_fit_worksheet_after_resize(self):
        ws=Workspace(); ws.resize(1500,900); ws.show_workspace(); ws.show(); self.app.processEvents()
        self.assertEqual(ws.plot_columns,3)
        ws.layout_plots(); width=ws.active.width()
        self.assertEqual(width,(ws.scroll.viewport().width()-28-6)//3)
        ws.resize(1800,900); self.app.processEvents(); ws.layout_plots()
        self.assertGreater(ws.active.width(),width)
        self.assertEqual(ws.active.width(),(ws.scroll.viewport().width()-28-6)//3)
        ws.set_plot_columns(4); self.assertEqual(ws.active.width(),(ws.scroll.viewport().width()-28-9)//4)
        ws.set_plot_columns(8); self.assertEqual(ws.plot_columns,5)
        ws.undo(); self.assertEqual(ws.plot_columns,4)
        ws.undo(); self.assertEqual(ws.plot_columns,3)
        ws.close()

    def test_small_plot_tick_labels_do_not_overlap_or_leave_widget(self):
        metrics=QFontMetricsF(QFont('Sans Serif',8))
        ticks=[(i,i*10000) for i in range(6)]
        labels=positioned_tick_labels(ticks,lambda pos:pos*20,metrics,100,False)
        self.assertGreaterEqual(len(labels),2)
        for i,(left,width,_) in enumerate(labels):
            self.assertGreaterEqual(left,0); self.assertLessEqual(left+width,100)
            if i: self.assertGreaterEqual(left,labels[i-1][0]+labels[i-1][1]+3)

    def test_backgating_only_colors_explicitly_colored_gates(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); plot=ws.active; plot.reset()
            ws.add_gate(plot,[[-10,-10],[10,-10],[10,10],[-10,10]])
            ws.backgate.setChecked(True)
            image=plot.density_image(ws.sample(),plot.axes()).convertToFormat(QImage.Format.Format_RGBA8888)
            pixels=bytes(image.bits())
            self.assertTrue(all(pixels[i]==pixels[i+1]==pixels[i+2] for i in range(0,len(pixels),4) if pixels[i+3]))
            ws.gates[0].color='#c23537'
            image=plot.density_image(ws.sample(),plot.axes()).convertToFormat(QImage.Format.Format_RGBA8888)
            pixels=bytes(image.bits())
            self.assertTrue(any(pixels[i]!=pixels[i+1] for i in range(0,len(pixels),4) if pixels[i+3]))
            ws.close()

    def test_dragging_plot_scrolls_into_new_empty_rows(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.resize(1500,800); ws.import_paths([str(source)]); ws.show_workspace(); ws.show(); self.app.processEvents()
            plot=ws.active; viewport=ws.scroll.viewport(); start=QPointF(plot.mapToGlobal(QPoint(80,10)))
            ws.begin_plot_preview(plot,start)
            pointer=viewport.mapToGlobal(QPoint(min(100,viewport.width()-1),viewport.height()-5))
            ws.update_plot_preview(plot,pointer)
            for _ in range(30): ws.scroll_plot_drag(); self.app.processEvents()
            self.assertGreater(ws.scroll.verticalScrollBar().value(),0)
            ws.move_plot(plot,pointer); self.assertGreater(plot.grid_slot,0)
            ws.end_plot_preview(); self.assertFalse(ws.plot_scroll_timer.isActive()); self.assertEqual(ws.canvas.minimumHeight(),0)
            ws.close()

    def test_drag_is_live_without_recomputing_statistics_and_undo(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); ws.add_gate(plot,[[1,2],[4,2],[4,5],[1,5]]); original=[v[:] for v in ws.gates[0].vertices]
            self.assertIsNone(ws.gates[0].color); self.assertEqual(ws.mode,'select')
            plot.grab(); start=plot.xy(2,3).toPoint(); end=plot.xy(2.5,3.5).toPoint()
            with patch('cytose.app.statistics',wraps=statistics) as calculate:
                QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start); calculate.reset_mock()
                QTest.mouseMove(plot,end); self.assertTrue(plot.drag_changed); self.assertNotEqual(ws.gates[0].vertices,original)
                self.assertEqual(calculate.call_count,0)
                QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end); self.assertGreater(calculate.call_count,0)
            ws.undo(); self.assertEqual(ws.gates[0].vertices,original)
            ws.undo(); self.assertFalse(ws.gates)
            ws.close()

    def test_rectangle_edge_resize_preserves_rectangle(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.show_workspace(); ws.resize(1500,900); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); ws.add_gate(plot,[[1,2],[4,2],[4,5],[1,5]])
            start=plot.xy(2.5,2).toPoint(); end=plot.xy(2.5,2.5).toPoint()
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
            QTest.mouseMove(plot,end); QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end)
            vertices=ws.gates[0].vertices; self.assertEqual(vertices[0][1],vertices[1][1]); self.assertGreater(vertices[0][1],2)
            self.assertTrue(plot.rectangle(ws.gates[0])); ws.close()

    def test_condition_enter_assigns_and_escape_clears_then_closes(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'A01 Test.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); dialog=Conditions(ws); dialog.show(); self.app.processEvents()
            dialog.search.setText('Test'); QTest.keyClick(dialog.search,Qt.Key.Key_Return)
            self.assertTrue(dialog.isVisible()); self.assertEqual(ws.samples[0].condition,'Test'); self.assertEqual(dialog.search.text(),'')
            dialog.search.setText('Test'); dialog.condition.setEditText('Custom'); QTest.keyClick(dialog.condition.lineEdit(),Qt.Key.Key_Return)
            self.assertTrue(dialog.isVisible()); self.assertEqual(ws.samples[0].condition,'Custom')
            dialog.search.setText('abc'); QTest.keyClick(dialog.search,Qt.Key.Key_Escape)
            self.assertTrue(dialog.isVisible()); self.assertEqual(dialog.search.text(),''); self.assertEqual(dialog.condition.currentText(),'')
            QTest.keyClick(dialog.search,Qt.Key.Key_Escape); self.assertFalse(dialog.isVisible()); ws.close()

    def test_long_condition_name_has_room(self):
        ws=Workspace(); ws.conditions=['Long experimental condition name 123456789']; dialog=Conditions(ws); dialog.show(); self.app.processEvents()
        editor=dialog.conditions.itemWidget(dialog.conditions.item(0)).findChild(QLineEdit)
        self.assertGreaterEqual(editor.width(),editor.fontMetrics().horizontalAdvance(editor.text())+8)
        dialog.close(); ws.close()

    def test_fluorescence_log_ticks(self):
        for name in ('FL1-A','FL-2','FL3-H','FL4-A'): self.assertTrue(log_scale(name))
        for name in ('FL1-W','FSC-A','FL5-A'): self.assertFalse(log_scale(name))
        ticks,minor=axis_ticks((0,5),True); values=[v for _,v in ticks]
        for value in (0,1,10,100,1000,10000): self.assertIn(value,values)
        self.assertTrue(minor)
        self.assertEqual(log_tick_label(100),'100'); self.assertEqual(log_tick_label(10000),'1e4')

    def test_density_uses_blue_to_red_palette(self):
        from PySide6.QtGui import QColor
        import numpy as np
        ws=Workspace(); ws.dark=False; events=np.array([[0.5,0.5]]); events.flags.writeable=False
        ws.samples=[Sample('sample.fcs',{},[Parameter('FSC-A'),Parameter('SSC-A')],events)]; ws.refresh()
        plot=ws.active; plot.axes(); plot.bounds=[(0,1),(0,1)]
        image=plot.density_image(ws.sample(),(0,1)); actual=image.pixelColor(128,127); expected=QColor.fromHsvF(0.64,0.78,0.78)
        for got,want in zip((actual.red(),actual.green(),actual.blue()),(expected.red(),expected.green(),expected.blue())): self.assertLessEqual(abs(got-want),1)
        ws.close()

    def test_clear_annotations_and_undo(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            ws.annotations={'FSC-A':'First','not-in-sample':'Other'}
            def accept_with_clear(dialog):
                next(button for button in dialog.findChildren(QPushButton) if button.text()=='Clear all labels').click()
                return QDialog.DialogCode.Accepted
            with patch.object(QDialog,'exec',accept_with_clear): ws.annotate()
            self.assertEqual(ws.annotations,{})
            ws.undo(); self.assertEqual(ws.annotations,{'FSC-A':'First','not-in-sample':'Other'}); ws.close()

    def test_undo_shortcut_removes_last_gate(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            plot=ws.active; plot.axes(); ws.add_gate(plot,[[1,2],[4,2],[4,5],[1,5]])
            plot.setFocus(); self.app.processEvents(); QTest.keyClick(plot,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
            self.assertFalse(ws.gates); ws.close()

    def test_sample_switch_does_not_recompute_comparison_and_cache_tracks_changes(self):
        with tempfile.TemporaryDirectory() as d:
            files=[Path(d)/f'A0{i} sample.fcs' for i in range(1,5)]
            for path in files: fixture(path)
            ws=Workspace(); ws.import_paths([str(path) for path in files]); ws.show(); self.app.processEvents()
            ws.add_gate(ws.active,[[0,0],[4,0],[4,5],[0,5]]); ws.pop.setCurrentIndex(1)
            self.assertEqual([row[2] for row in ws.comparison_rows()],[2,2,2,2])
            with patch.object(ws,'refresh_comparison',wraps=ws.refresh_comparison) as comparison:
                ws.sample_list.setCurrentRow(1); self.assertEqual(comparison.call_count,0)
            self.assertEqual([row[2] for row in ws.comparison_rows()],[2,2,2,2])
            ws.gates[0].vertices=[[2,3],[6,3],[6,7],[2,7]]; ws.refresh()
            self.assertEqual([row[2] for row in ws.comparison_rows()],[4,4,4,4])
            ws.samples[0].condition='Control'; ws.refresh(); self.assertEqual(ws.comparison_rows()[0][1],'Control')
            ws.undo(); self.assertEqual([row[2] for row in ws.comparison_rows()],[3,3,3,3])
            ws.close()

    def test_recent_plot_density_is_reused_and_gate_changes_invalidate_child(self):
        with tempfile.TemporaryDirectory() as d:
            files=[Path(d)/f'sample{i}.fcs' for i in range(2)]
            for path in files: fixture(path)
            ws=Workspace(); ws.import_paths([str(path) for path in files]); plot=ws.active; plot.axes(); plot.reset()
            with patch.object(plot,'_make_density',wraps=plot._make_density) as make:
                first=plot.density_image(ws.samples[0],(0,1)); plot.density_image(ws.samples[1],(0,1))
                self.assertIs(plot.density_image(ws.samples[0],(0,1)),first); self.assertEqual(make.call_count,2)
                ws.add_gate(plot,[[0,0],[4,0],[4,5],[0,5]])
                plot.density_image(ws.samples[0],(0,1)); self.assertEqual(make.call_count,2)
                plot.population=ws.gates[0].id; plot.density_image(ws.samples[0],(0,1)); self.assertEqual(make.call_count,3)
                ws.gates[0].vertices=[[2,3],[6,3],[6,7],[2,7]]
                plot.density_image(ws.samples[0],(0,1)); self.assertEqual(make.call_count,4)
            ws.close()

    def test_plot_titles_wrap_and_axis_labels_are_symmetric(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.resize(1300,800); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); ws.add_gate(plot,[[1,2],[4,2],[4,5],[1,5]])
            ws.gates[0].name='A very long population name with several words and an exceptionallylongunbrokenidentifier'
            ws.open_gate(ws.gates[0].id); self.app.processEvents(); child=ws.active
            layout,height=title_layout(child.title_text(),child.font(),max(1,child.width()-105*ws.plot_zoom))
            self.assertGreater(layout.lineCount(),1)
            self.assertGreater(height,child.fontMetrics().height()); self.assertGreaterEqual(ws.plot_title_height,height+8*ws.plot_zoom)
            self.assertEqual(plot.plot_rect().top(),child.plot_rect().top())
            x,y=child.axis_label_rects(); r=child.plot_rect()
            x_gap=x.top()-(r.bottom()+21*ws.plot_zoom)
            y_gap=(r.left()-7*ws.plot_zoom-child.y_tick_width())-y.right()
            self.assertAlmostEqual(x_gap,y_gap)
            self.assertEqual(x.height(),y.width())
            self.assertLessEqual(r.right(),child.width()-27*ws.plot_zoom)
            ws.close()

    def test_axis_title_spacing_tracks_wide_y_tick_labels(self):
        ws=Workspace(); plot=ws.active; plot.resize(360,380)
        for bounds,name in [((0.,1.),'SSC-A'),((-1000000.,1000000.),'SSC-A'),((-8.,8.),'FL1-A')]:
            plot.y=name; plot.bounds=[(0.,1.),bounds]
            r=plot.plot_rect(); x,y=plot.axis_label_rects()
            self.assertAlmostEqual(x.top()-(r.bottom()+21*ws.plot_zoom),(r.left()-7*ws.plot_zoom-plot.y_tick_width())-y.right())
            self.assertGreaterEqual(y.left(),0)
        ws.close()

    def test_axis_title_rotation_preserves_color_and_pixel_coverage(self):
        ws=Workspace(); plot=ws.active
        for color in (QColor('#eeeeee'),QColor('#202020')):
            horizontal=plot.axis_label_image('FSC-A',color,215,18)
            vertical=plot.axis_label_image('FSC-A',color,215,18,vertical=True)
            self.assertEqual((horizontal.width(),horizontal.height()),(vertical.height(),vertical.width()))
            pixels=lambda image: sorted(image.pixel(x,y) for y in range(image.height()) for x in range(image.width()))
            self.assertEqual(pixels(horizontal),pixels(vertical))
        ws.close()

    def test_gate_can_move_beyond_plot_in_log_view(self):
        import numpy as np
        ws=Workspace(); events=np.array([[1.,0.],[1000.,.5],[100000.,1.]])
        events.flags.writeable=False; ws.samples=[Sample('sample.fcs',{},[Parameter('FL1-A'),Parameter('SSC-A')],events)]
        ws.show_workspace(); ws.refresh(); ws.show(); self.app.processEvents()
        plot=ws.active; plot.x='FL1-A'; plot.y='SSC-A'; plot.bounds=[(0,5),(0,1)]
        ws.add_gate(plot,[[100.,.2],[10000.,.2],[10000.,.8],[100.,.8]])
        start=plot.xy(1000.,.5).toPoint(); end=QPoint(plot.width()+250,-200)
        QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start); QTest.mouseMove(plot,end); QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end)
        points=[plot.xy(x,y) for x,y in ws.gates[0].vertices]
        self.assertTrue(any(point.x()>plot.plot_rect().right() for point in points))
        self.assertTrue(any(point.y()<plot.plot_rect().top() for point in points))
        before=[v[:] for v in ws.gates[0].vertices]; plot.bounds=[(2,3),(.4,.6)]; plot.grab()
        self.assertEqual(ws.gates[0].vertices,before)  # Zooming only clips the display.
        ws.close()

    def test_rectangle_corner_and_edge_can_leave_linear_plot(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); ws.add_gate(plot,[[2,3],[4,3],[4,5],[2,5]])
            corner=plot.xy(2,3).toPoint(); outside=QPoint(-200,plot.height()+200)
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,corner); QTest.mouseMove(plot,outside); QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,outside)
            self.assertTrue(plot.rectangle(ws.gates[0]))
            self.assertTrue(any(not plot.plot_rect().contains(plot.xy(x,y)) for x,y in ws.gates[0].vertices))
            ws.undo(); plot=ws.active
            edge=QPointF((plot.xy(*ws.gates[0].vertices[0]).x()+plot.xy(*ws.gates[0].vertices[1]).x())/2,plot.xy(*ws.gates[0].vertices[0]).y()).toPoint()
            outside=QPoint(edge.x(),plot.height()+200)
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,edge); QTest.mouseMove(plot,outside); QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,outside)
            self.assertTrue(plot.rectangle(ws.gates[0]))
            self.assertTrue(any(not plot.plot_rect().contains(plot.xy(x,y)) for x,y in ws.gates[0].vertices))
            ws.close()

    def test_gate_outside_plot_is_clipped_and_fully_outside_label_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); ws.add_gate(plot,[[2,3],[7,3],[7,5],[2,5]])
            self.app.processEvents(); image=plot.grab().toImage(); ratio=image.devicePixelRatio()
            x=int((plot.plot_rect().right()+5)*ratio); y=int(plot.xy(3,3).y()*ratio); color=image.pixelColor(x,y)
            self.assertFalse(color.red()>150 and color.green()<100 and color.blue()<100)
            ws.gates[0].vertices=[[6,3],[7,3],[7,5],[6,5]]; plot.update(); self.app.processEvents(); plot.grab()
            self.assertNotIn(ws.gates[0].id,plot.label_hits); ws.close()

    def test_dark_default_and_saved_light_mode(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source); project=Path(d)/'analysis.cytose'
            ws=Workspace(); self.assertTrue(ws.dark); ws.import_paths([str(source)]); ws.toggle_theme(); self.assertFalse(ws.dark)
            ws.project_path=str(project); ws.timer.stop(); self.assertTrue(ws.autosave())
            restored=Workspace(); restored.load_project(project); self.assertFalse(restored.dark)
            document=json.loads(project.read_text()); document.pop('dark'); project.write_text(json.dumps(document))
            legacy=Workspace(); legacy.load_project(project); self.assertTrue(legacy.dark)
            ws.timer.stop(); restored.timer.stop(); legacy.timer.stop(); ws.close(); restored.close(); legacy.close()

    def test_tick_numbers_use_smaller_same_family_font(self):
        axis=QFont('Comfortaa'); axis.setPointSizeF(10)
        numbers=tick_font(axis); self.assertEqual(numbers.family(),axis.family()); self.assertLess(numbers.pointSizeF(),axis.pointSizeF())
        axis.setPixelSize(12); numbers=tick_font(axis); self.assertEqual(numbers.family(),axis.family()); self.assertEqual(numbers.pixelSize(),10)

    def test_axis_menu_uses_channel_or_annotation_without_stain_duplication(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            plot=ws.active; plot.axes(); plot.reset()
            for parameter in ws.sample().parameters: parameter.stain=parameter.name
            ws.annotations={'FSC-A':'Cells','SSC-A':'SSC-A'}
            labels=[action.text() for action in plot.make_axis_menu('x').actions()]
            self.assertEqual(labels,['FSC-A · Cells','SSC-A']); ws.close()

    def test_analysis_defaults_and_annotation_label(self):
        import numpy as np
        ws=Workspace(); ws.show_workspace()
        self.assertEqual(ws.parameter.currentData(),'FL1-A')
        self.assertEqual(ws.parameter.currentText(),'FL1-A')
        events=np.array([[1.,2.]],dtype=np.float64); events.flags.writeable=False
        ws.samples=[Sample('sample.fcs',{},[Parameter('FSC-A'),Parameter('FL1-A')],events)]
        ws.refresh(); self.assertEqual(ws.parameter.currentData(),'FL1-A')
        ws.annotations={'FL1-A':'A particularly long annotated fluorescence marker'}; ws.refresh()
        self.assertEqual(ws.parameter.currentText(),'A particularly long annotated fluorescence marker')
        self.assertEqual(ws.chart.minimumHeight(),200)
        ws.close()

    def test_welcome_quick_analysis_opens_workspace_without_picker(self):
        ws=Workspace(); choices=ws.welcome_page.findChildren(WelcomeChoice)
        margins=ws.welcome_page.layout().contentsMargins(); self.assertEqual((margins.left(),margins.top(),margins.right(),margins.bottom()),(7,7,7,7))
        self.assertEqual(ws.welcome_page.layout().itemAt(0).widget().objectName(),'panelTile')
        self.assertEqual(len(choices),3)
        with patch('cytose.app.QFileDialog.getOpenFileNames') as picker:
            next(choice for choice in choices if choice.title=='Quick analysis').click()
            picker.assert_not_called()
        self.assertIs(ws.pages.currentWidget(),ws.workspace_page); self.assertFalse(ws.samples); ws.close()

    def drop(self,widget,paths,pos):
        mime=sample_mime(paths)  # QDropEvent does not own its data; keep it alive for the drop.
        event=QDropEvent(QPointF(pos),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        widget.dropEvent(event); return event

    def test_overlay_drag_drop_legend_undo_and_project_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            sources=[Path(d)/f'A0{i} sample.fcs' for i in (1,2,3)]
            for source in sources: fixture(source)
            ws=Workspace(); ws.import_paths([str(source) for source in sources]); ws.resize(1500,900); ws.show(); self.app.processEvents()
            paths=[sample.path for sample in ws.samples]; listing=ws.sample_list
            self.drop(listing,[paths[1]],listing.visualItemRect(listing.item(1)).center())
            self.assertEqual(ws.overlays,[]); self.assertEqual(ws.sheet_stack.currentIndex(),0)
            self.drop(listing,[paths[1]],listing.visualItemRect(listing.item(0)).center())
            overlay=ws.overlays[0]; self.assertEqual([e['path'] for e in overlay['entries']],paths[:2])
            self.assertEqual(ws.current_overlay,overlay['id']); self.assertIs(ws.sheet_stack.currentWidget(),ws.overlay_view)
            self.assertFalse(ws.tool_buttons['rectangle'].isEnabled()); self.assertTrue(ws.tool_buttons['rectangle'].isVisible()); self.assertEqual(ws.current_sample_label.text(),'Overlay 1')
            self.assertEqual(overlay['kind'],'histogram'); self.assertNotIn('normalized',overlay); self.assertEqual(overlay['x'],'FSC-A')
            self.assertNotEqual(overlay['entries'][0]['color'],overlay['entries'][1]['color'])
            overlays=ws.overlay_list; self.drop(overlays,[paths[2],paths[0]],overlays.visualItemRect(overlays.item(0)).center())
            self.assertEqual([e['path'] for e in overlay['entries']],paths); self.assertEqual(ws.overlay_view.legend.count(),3)
            self.assertIn('3 events',ws.overlay_view.legend.item(0).text())
            model=ws.overlay_view.legend.model(); model.moveRow(model.index(0,0).parent(),2,model.index(0,0).parent(),0)
            self.assertEqual([e['path'] for e in overlay['entries']],[paths[2],paths[0],paths[1]])
            ws.overlay_view.legend.item(0).setCheckState(Qt.CheckState.Unchecked); self.assertFalse(overlay['entries'][0]['visible'])
            self.assertEqual(len(ws.overlay_view.graph.data[2]),2)
            ws.undo(); ws.undo(); self.assertEqual([e['path'] for e in ws.overlay(overlay['id'])['entries']],paths); self.assertEqual(ws.current_overlay,overlay['id'])
            ws.overlay_view.kind.setCurrentIndex(ws.overlay_view.kind.findData('scatter')); self.app.processEvents()
            self.assertEqual(ws.overlay(overlay['id'])['kind'],'scatter'); self.assertTrue(ws.overlay_view.graph.control_active('opacity')); self.assertFalse(ws.overlay_view.graph.control_active('offset'))
            self.assertEqual(ws.overlay_view.graph.data[0],'scatter'); self.assertEqual(len(ws.overlay_view.graph.data[2]),3)
            self.assertFalse(ws.overlay_view.graph.grab().isNull())
            self.drop(overlays,[paths[0]],QPoint(10,overlays.viewport().height()-5)); self.assertEqual(len(ws.overlays),2)
            ws.duplicate_overlay(overlay['id']); self.assertEqual(ws.overlays[1]['name'],'Overlay 1 copy'); self.assertEqual(ws.current_overlay,ws.overlays[1]['id'])
            ws.remove_overlay(ws.overlays[1]['id']); self.assertEqual(len(ws.overlays),2); self.assertIsNone(ws.current_overlay); self.assertTrue(ws.tool_buttons['rectangle'].isEnabled())
            ws.show_overlay(overlay['id']); ws.overlay_view.legend.itemDoubleClicked.emit(ws.overlay_view.legend.item(2))
            self.assertIsNone(ws.current_overlay); self.assertEqual(ws.sample_list.currentRow(),2); self.assertEqual(ws.current_sample_label.text(),ws.samples[2].name)
            ws.add_gate(ws.active,[[0,0],[4,0],[4,5],[0,5]]); gid=ws.gates[0].id
            ws.show_overlay(overlay['id']); ws.overlay_view.population.setCurrentIndex(ws.overlay_view.population.findData(gid))
            self.assertEqual(ws.overlay(overlay['id'])['population'],gid); self.assertIn('2 events',ws.overlay_view.legend.item(0).text())
            project=Path(d)/'overlay.cytose'; ws.project_path=str(project); self.assertTrue(ws.autosave())
            restored=Workspace(); restored.load_project(project); self.app.processEvents()
            self.assertEqual(restored.overlays,ws.overlays); self.assertEqual(restored.current_overlay,overlay['id']); self.assertIs(restored.sheet_stack.currentWidget(),restored.overlay_view)
            self.assertEqual(restored.overlay_list.count(),2); self.assertEqual(restored.overlay_view.graph.data[0],'scatter')
            ws.delete_gate(gid); self.assertIsNone(ws.overlay(overlay['id'])['population']); self.assertEqual(ws.overlay_view.population.currentIndex(),0)
            ws.timer.stop(); restored.timer.stop(); ws.close(); restored.close()

    def test_overlay_missing_samples_relink_and_condition_tab(self):
        with tempfile.TemporaryDirectory() as d:
            sources=[Path(d)/f'A0{i} sample.fcs' for i in (1,2)]
            for source in sources: fixture(source)
            window=MainWindow(); ws=window.tabs.currentWidget(); ws.import_paths([str(source) for source in sources])
            ws.samples[0].condition='Control'; oid=ws.create_overlay([s.path for s in ws.samples])
            window.open_condition(ws,'Control'); child=window.tabs.currentWidget()
            self.assertEqual([e['path'] for e in child.overlays[0]['entries']],[ws.samples[0].path])
            project=Path(d)/'p.cytose'; ws.project_path=str(project); ws.autosave(); ws.timer.stop()
            moved=Path(d)/'moved'; moved.mkdir(); sources[1].rename(moved/sources[1].name)
            with patch('cytose.app.QMessageBox.warning'): restored=Workspace(); restored.load_project(project); self.app.processEvents()
            self.assertEqual(len(restored.samples),1); self.assertIn('(missing)',restored.overlay_view.legend.item(1).text())
            self.assertIn(sources[1].name,restored.overlay_view.graph.data[3])
            with patch('cytose.app.QFileDialog.getOpenFileName',return_value=(str(moved/sources[1].name),'FCS')): restored.relink_missing()
            self.assertEqual(restored.overlay(oid)['entries'][1]['path'],str((moved/sources[1].name).resolve())); self.assertEqual(restored.overlay_view.graph.data[3],[])
            restored.timer.stop(); restored.close()
            with patch('cytose.app.QMessageBox.question',return_value=QMessageBox.StandardButton.Discard): window.close()

    def test_overlay_plot_is_square_with_switches_offset_and_zoom(self):
        with tempfile.TemporaryDirectory() as d:
            sources=[Path(d)/f'A0{i} sample.fcs' for i in (1,2,3)]
            for source in sources: fixture(source)
            ws=Workspace(); ws.import_paths([str(source) for source in sources]); ws.resize(1500,900); ws.show()
            oid=ws.create_overlay([s.path for s in ws.samples]); self.app.processEvents(); view=ws.overlay_view; graph=view.graph; overlay=ws.overlay(oid)
            rect=graph.plot_rect(); self.assertEqual(rect.width(),rect.height()); self.assertEqual(overlay['offset'],0.)
            self.assertEqual(graph.hit(graph.title_rect(rect).center()),'population'); self.assertEqual(graph.hit(graph.x_title_rect(rect).center()),'x')
            self.assertEqual(graph.lane_layout(rect,3)[2](2),rect.bottom())
            self.assertTrue(graph.control_active('offset')); graph.set_bar('offset',1.); self.assertEqual(overlay['offset'],1.)
            offset,lane,base=graph.lane_layout(rect,3); self.assertAlmostEqual(lane,rect.height()/3); self.assertAlmostEqual(base(0),rect.top()+lane)
            self.assertFalse(graph.export_image().isNull()); self.assertFalse(graph.exporting)
            graph.zoom_to(QRectF(rect.left()+rect.width()/4,rect.top()+10,rect.width()/2,20)); self.assertIsNone(overlay['zoom'][1]); self.assertEqual(len(overlay['zoom'][0]),2)
            ws.undo(); self.assertIsNone(ws.overlay(oid)['zoom']); ws.undo(); overlay=ws.overlay(oid); self.assertEqual(overlay['offset'],0.)
            QTest.mouseClick(graph,Qt.MouseButton.LeftButton,pos=graph.control_rects()['kind'].center().toPoint()); overlay=ws.overlay(oid)
            self.assertEqual(overlay['kind'],'scatter'); self.assertEqual(graph.hit(graph.y_title_rect(graph.plot_rect()).center()),'y'); self.assertFalse(graph.control_active('offset')); self.assertNotIn('offset',graph.control_rects())
            rect=graph.plot_rect(); before=graph.data[1]
            graph.zoom_to(QRectF(rect.left()+rect.width()/4,rect.top()+rect.height()/4,rect.width()/2,rect.height()/2))
            zoom=ws.overlay(oid)['zoom']; self.assertLess(zoom[0][1]-zoom[0][0],before[0][1]-before[0][0]); self.assertLess(zoom[1][1]-zoom[1][0],before[1][1]-before[1][0])
            self.assertEqual([list(axis) for axis in graph.data[1]],zoom)
            ws.reset_zoom(); self.assertIsNone(ws.overlay(oid)['zoom'])
            ws.overlay(oid)['zoom']=zoom; view.y.setCurrentIndex(1-view.y.currentIndex()); self.assertIsNone(ws.overlay(oid)['zoom'])
            ws.close()

    def test_overlay_modal_histogram_and_contour_levels(self):
        with tempfile.TemporaryDirectory() as d:
            sources=[Path(d)/f'A0{i} sample.fcs' for i in (1,2)]
            for source in sources: fixture(source)
            ws=Workspace(); ws.import_paths([str(source) for source in sources]); ws.resize(1500,900); ws.show()
            oid=ws.create_overlay([s.path for s in ws.samples]); self.app.processEvents(); view=ws.overlay_view; graph=view.graph
            self.assertEqual(graph.hit(graph.control_rects()['scale'].center()),'scale'); self.assertNotIn('style',graph.control_rects())
            QTest.mouseClick(graph,Qt.MouseButton.LeftButton,pos=graph.control_rects()['scale'].center().toPoint())
            self.assertEqual(ws.overlay(oid)['scale'],'modal'); self.assertTrue(all(counts.max()==100 for _,_,counts,_ in graph.data[2]))
            graph.toggle('kind'); self.assertFalse(graph.control_active('scale')); self.assertFalse(graph.control_active('levels'))
            graph.toggle('style'); self.assertEqual(ws.overlay(oid)['style'],'contour'); self.assertEqual(graph.data[0],'contour')
            self.assertTrue(graph.control_active('levels')); self.assertTrue(graph.control_active('opacity'))
            bar=graph.control_rects()['levels']; QTest.mouseClick(graph,Qt.MouseButton.LeftButton,pos=QPoint(round(bar.left()+bar.width()*0.15),round(bar.center().y()))); self.assertEqual(ws.overlay(oid)['levels'],3); self.assertLessEqual(len(graph.data[2][0][1]),3)
            self.assertFalse(graph.export_image().isNull())
            ws.undo(); self.assertEqual(ws.overlay(oid)['levels'],5); ws.undo(); self.assertEqual(ws.overlay(oid)['style'],'density')
            ws.close()

    def test_imported_samples_are_listed_in_natural_order(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('B1 x.fcs','A10 x.fcs','A2 x.fcs'): fixture(Path(d)/name)
            ws=Workspace(); ws.import_paths([str(Path(d)/'B1 x.fcs')]); ws.import_paths([d])
            self.assertEqual([s.name for s in ws.samples],['A2 x.fcs','A10 x.fcs','B1 x.fcs'])
            self.assertEqual([ws.sample_list.item(i).text() for i in range(3)],['A2 x.fcs','A10 x.fcs','B1 x.fcs']); ws.close()

    def test_ellipse_gate_draw_resize_and_redo(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'A01 sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.resize(1500,900); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); r=plot.plot_rect()
            QTest.keyClick(ws,Qt.Key.Key_4); self.assertEqual(ws.mode,'ellipse')
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,pos=QPoint(round(r.left()+5),round(r.bottom()-5)))
            QTest.mouseMove(plot,QPoint(round(r.center().x()),round(r.center().y())))
            QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,pos=QPoint(round(r.center().x()),round(r.center().y())))
            gate=ws.gates[0]; self.assertEqual(gate.shape,'ellipse'); self.assertEqual(len(gate.vertices),48); self.assertEqual(ws.mode,'select')
            x0,x1,y0,y1=plot.ellipse_box(gate)
            right=plot.xy(*gate.vertices[0]); plot.selected,plot.edit_vertex=plot.gate_at(right); self.assertEqual(plot.edit_vertex,0)
            self.assertIsNone(plot.gate_at(plot.xy(*gate.vertices[5]))[1])
            ws.checkpoint(); plot.start=plot.raw(right); plot.drag_changed=True
            QTest.mouseMove(plot,QPoint(round(right.x()+20),round(right.y())))
            nx0,nx1,ny0,ny1=plot.ellipse_box(ws.gates[0]); self.assertAlmostEqual(nx0,x0,delta=(x1-x0)*.02); self.assertGreater(nx1,x1); self.assertAlmostEqual(ny1,y1,delta=(y1-y0)*.02)
            self.assertIsNotNone(statistics(ws.samples[0],ws.gates,gate.id,'FSC-A')['count'])
            self.assertFalse(ws.redo_button.isEnabled()); ws.undo(); self.assertTrue(ws.redo_button.isEnabled())
            self.assertAlmostEqual(plot.ellipse_box(ws.gates[0])[1],x1,delta=(x1-x0)*.02)
            ws.redo(); self.assertGreater(plot.ellipse_box(ws.gates[0])[1],x1); self.assertFalse(ws.redo_button.isEnabled())
            ws.undo(); ws.undo(); self.assertEqual(ws.gates,[]); ws.redo(); self.assertEqual(ws.gates[0].shape,'ellipse')
            ws.checkpoint(); self.assertFalse(ws.redo_button.isEnabled()); self.assertEqual(ws.future,[])
            ws.close()

    def test_ellipse_rotates_and_zoom_steps_back(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'A01 sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.resize(1500,900); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); r=plot.plot_rect(); (a,b),(c,d)=plot.bounds
            ws.add_gate(plot,plot.ellipse_vertices(a+(b-a)*.2,a+(b-a)*.7,c+(d-c)*.4,c+(d-c)*.6),'ellipse')
            gate=ws.gates[0]; plot.selected=gate.id; center,u,rx,v,ry=plot.ellipse_frame(gate)
            knob=plot.rotate_handle(gate); self.assertEqual(plot.gate_at(knob),(gate.id,plot.ELLIPSE_ROTATE))
            plot.edit_vertex=plot.ELLIPSE_ROTATE; plot.start=plot.raw(knob); plot.drag_changed=True
            QTest.mouseMove(plot,QPoint(round(center[0]+rx+40),round(center[1])))
            _,nu,nrx,_,nry=plot.ellipse_frame(ws.gates[0]); self.assertAlmostEqual(nrx,rx,delta=1); self.assertAlmostEqual(nry,ry,delta=1)
            self.assertGreater(abs(nu[1]),0.9)
            ws.gates=[]; ws.add_gate(plot,plot.ellipse_vertices(a+(b-a)*.3,a+(b-a)*.6,c+(d-c)*.7,c+(d-c)*.98),'ellipse'); top=ws.gates[0]; center=plot.ellipse_frame(top)[0]
            # Real clicks reach the window before the plot, so send them that way.
            window=ws.window().windowHandle(); at=lambda point:plot.mapTo(ws.window(),point)
            QTest.mouseClick(window,Qt.MouseButton.LeftButton,pos=at(QPoint(round(center[0]),round(center[1])))); self.app.processEvents(); self.assertEqual(plot.selected,top.id)
            knob=plot.rotate_handle(top); self.assertTrue(plot.plot_rect().contains(knob)); self.assertGreater(knob.y(),center[1])
            QTest.mousePress(window,Qt.MouseButton.LeftButton,pos=at(knob.toPoint())); self.app.processEvents(); self.assertEqual(plot.edit_vertex,plot.ELLIPSE_ROTATE); QTest.mouseMove(plot,QPoint(round(center[0]+120),round(center[1])))
            QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,pos=QPoint(round(center[0]+120),round(center[1])))
            self.assertEqual(plot.selected,top.id); self.assertGreater(abs(plot.ellipse_frame(ws.gates[0])[1][1]),0.9)
            ws.set_mode('zoom'); full=plot.bounds
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,pos=QPoint(round(r.left()+10),round(r.top()+10)))
            QTest.mouseMove(plot,QPoint(round(r.center().x()),round(r.center().y())))
            QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,pos=QPoint(round(r.center().x()),round(r.center().y())))
            first=plot.bounds; self.assertNotEqual(first,full)
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,pos=QPoint(round(r.left()+10),round(r.top()+10)))
            QTest.mouseMove(plot,QPoint(round(r.center().x()),round(r.center().y())))
            QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,pos=QPoint(round(r.center().x()),round(r.center().y())))
            QTest.mouseDClick(plot,Qt.MouseButton.LeftButton,pos=QPoint(round(r.center().x()),round(r.center().y()))); self.assertEqual(plot.bounds,first)
            ws.open_gate(gate.id); child=ws.plots[1]; child.bounds=[(0.,1.),(0.,1.)]
            ws.reset_zoom(); self.assertEqual(plot.bounds,full); self.assertNotEqual(child.bounds,[(0.,1.),(0.,1.)]); self.assertEqual(plot.zoom_history,[])
            ws.close()

    def test_plot_size_buttons_scale_overlay_plot(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'A01 sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.resize(1500,900); ws.show(); ws.create_overlay([ws.samples[0].path]); self.app.processEvents()
            graph=ws.overlay_view.graph; before=graph.plot_rect().width(); graph.setFocus()
            self.assertTrue(ws.toolbar_actions[6].isEnabled()); QTest.keyClick(ws,Qt.Key.Key_Equal); self.assertGreater(graph.plot_rect().width(),before)
            QTest.keyClick(ws,Qt.Key.Key_Minus); QTest.keyClick(ws,Qt.Key.Key_Minus); self.assertLess(graph.plot_rect().width(),before)
            QTest.keyClick(ws,Qt.Key.Key_Z); QTest.keyClick(ws,Qt.Key.Key_Z); self.assertEqual(ws.plot_columns,2)
            QTest.keyClick(ws,Qt.Key.Key_X); self.assertEqual(ws.plot_columns,3)
            ws.sample_list.setFocus(); QTest.keyClick(ws.sample_list,Qt.Key.Key_Up); self.assertEqual(ws.plot_columns,3)
            self.assertFalse(ws.backgate.isEnabled()); ws.close()

    def test_low_event_samples_show_warning(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('A1 x.fcs','A2 x.fcs'): fixture(Path(d)/name)
            ws=Workspace(); ws.show_workspace(); ws.import_paths([d]); ws.show(); self.app.processEvents()
            self.assertTrue(ws.event_warning.isVisible()); self.assertEqual(ws.event_warning.text(),'● 2 samples with fewer than 10,000 events in All Events')
            self.assertIn('Fewer than',ws.sample_list.item(0).toolTip())
            with patch('cytose.app.LOW_EVENTS',3):
                ws.add_gate(ws.active,[[0,0],[4,0],[4,5],[0,5]]); ws.pop.setCurrentIndex(1)
                self.assertEqual(ws.event_warning.text(),'● 2 samples with fewer than 3 events in Cells')
                ws.pop.setCurrentIndex(0); self.assertFalse(ws.event_warning.isVisible())
            ws.create_overlay([s.path for s in ws.samples]); self.assertEqual(ws.overlay_list.item(0).text(),'Overlay 1'); ws.close()

    def test_sample_specific_gating_group_all_and_reset(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('A1 x.fcs','A2 x.fcs','A3 x.fcs'): fixture(Path(d)/name)
            ws=Workspace(); ws.show_workspace(); ws.import_paths([d]); ws.resize(1500,900); ws.show(); self.app.processEvents()
            a,b,c=ws.samples; a.condition=b.condition='Ctrl'; c.condition='Drug'; ws.refresh()
            ws.add_gate(ws.active,[[0,0],[4,0],[4,5],[0,5]]); gid=ws.gates[0].id; ws.pop.setCurrentIndex(1); ws.metric_combo.setCurrentText('% of parent')
            count=lambda sample:statistics(sample,ws.gates_for(sample),gid,'FSC-A')['count']
            self.assertEqual([count(s) for s in ws.samples],[2,2,2]); self.assertFalse(ws.unique_warning.isVisible())
            QTest.keyClick(ws,Qt.Key.Key_U); self.assertIn(a.path,ws.sample_gates); self.assertTrue(ws.gating_buttons[0].isChecked())
            ws.gates[0].vertices=[[0,0],[2,0],[2,5],[0,5]]; ws.refresh()
            self.assertEqual([count(s) for s in ws.samples],[1,2,2]); self.assertEqual([round(r[2]) for r in ws.comparison_rows()],[33,67,67])
            self.assertEqual(ws.unique_warning.text(),'● 1 sample with unique gating'); self.assertIn('unique gating',ws.current_sample_label.text())
            ws.sample_list.setCurrentRow(2); self.assertEqual(ws.gates[0].vertices,[[0,0],[4,0],[4,5],[0,5]]); self.assertFalse(ws.gating_buttons[0].isChecked())
            c.condition='Unassigned'; ws.refresh(); self.assertFalse(ws.gating_buttons[1].isEnabled()); QTest.keyClick(ws,Qt.Key.Key_C); self.assertNotIn(c.path,ws.sample_gates); c.condition='Drug'; ws.refresh(); self.assertTrue(ws.gating_buttons[1].isEnabled())
            ws.sample_list.setCurrentRow(0); QTest.keyClick(ws,Qt.Key.Key_C)
            self.assertEqual([count(s) for s in ws.samples],[1,1,2]); self.assertEqual(set(ws.sample_gates),{a.path,b.path}); self.assertIn('2 samples',ws.unique_warning.text())
            # Detach the project afterwards so later edits cannot autosave into the deleted temporary folder.
            project=Path(d)/'p.cytose'; ws.project_path=str(project); ws.autosave(); ws.timer.stop(); ws.project_path=None
            restored=Workspace(); restored.load_project(project); self.assertEqual(set(restored.sample_gates),{a.path,b.path})
            self.assertEqual([statistics(s,restored.gates_for(s),gid,'FSC-A')['count'] for s in restored.samples],[1,1,2]); restored.timer.stop(); restored.close()
            ws.sample_list.setCurrentRow(1); QTest.keyClick(ws,Qt.Key.Key_U); self.assertEqual([count(s) for s in ws.samples],[1,2,2]); self.assertFalse(ws.gating_buttons[0].isChecked())
            ws.undo(); self.assertEqual([count(s) for s in ws.samples],[1,1,2])
            ws.sample_list.setCurrentRow(0); QTest.keyClick(ws,Qt.Key.Key_A); self.assertEqual(ws.sample_gates,{}); self.assertEqual([count(s) for s in ws.samples],[1,1,1])
            self.assertFalse(ws.unique_warning.isVisible())
            ws.create_overlay([s.path for s in ws.samples]); self.assertFalse(any(button.isEnabled() for button in ws.gating_buttons)); ws.close()

    def test_gate_dialog_swatches(self):
        ws=Workspace(); plain=GateDialog(ws,'G1',None); self.assertTrue(plain.default.isChecked()); self.assertFalse(plain.custom.isChecked()); plain.close()
        ws=Workspace(); dialog=GateDialog(ws,'Q3','#0385ae'); swatches=dialog.swatches.buttons()
        self.assertTrue(swatches[2].isChecked()); swatches[3].click(); self.assertEqual(dialog.color,'#058f60')
        swatches[0].click(); self.assertIsNone(dialog.color)
        with patch('cytose.app.QColorDialog.getColor',return_value=QColor('#123456')): dialog.custom.click()
        self.assertEqual(dialog.color,'#123456'); self.assertTrue(dialog.custom.isChecked())
        with patch('cytose.app.QColorDialog.getColor',return_value=QColor()): swatches[1].click(); dialog.custom.click()
        self.assertEqual(dialog.color,'#c23537'); self.assertTrue(swatches[1].isChecked()); dialog.close(); ws.close()

    def test_dialogs_share_done_footer(self):
        from cytose.dialogs import ask_name
        ws=Workspace(); dialog=GateDialog(ws,'G1',None); done=[b for b in dialog.findChildren(QPushButton) if b.text()=='Done']
        self.assertEqual(len(done),1); self.assertTrue(done[0].isDefault()); self.assertFalse([b for b in dialog.findChildren(QPushButton) if b.text() in ('OK','Cancel')]); dialog.close()
        conditions=Conditions(ws); self.assertEqual([b.text() for b in conditions.findChildren(QPushButton) if b.text()=='Done'],['Done']); conditions.close()
        with patch('cytose.dialogs.QDialog.exec',return_value=1): self.assertEqual(ask_name(ws,'Rename','  New  '),'New')
        with patch('cytose.dialogs.QDialog.exec',return_value=0): self.assertIsNone(ask_name(ws,'Rename','New'))
        ws.close()

    def test_file_dialogs_start_in_last_folder(self):
        from cytose.dialogs import remembered, start_folder
        with tempfile.TemporaryDirectory() as d:
            remembered(('',''))
            with tempfile.TemporaryDirectory() as other:
                self.assertEqual(remembered((str(Path(other)/'x.cytose'),'')),(str(Path(other)/'x.cytose'),'')); self.assertEqual(start_folder(),str(Path(other)))
            desktop=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
            self.assertEqual(start_folder(),desktop if Path(desktop).is_dir() else str(Path.home()))
            remembered(([str(Path(d)/'a.fcs')],'')); self.assertEqual(start_folder(),str(Path(d)))
            ws=Workspace()
            with patch('cytose.app.QFileDialog.getOpenFileName',return_value=('','')) as picker: ws.open_project_here()
            self.assertEqual(picker.call_args[0][2],str(Path(d)))
            with patch('cytose.app.QFileDialog.getSaveFileName',return_value=('','')) as picker: ws.new_project()
            import datetime; self.assertEqual(picker.call_args[0][2],str(Path(d)/f'{datetime.date.today():%Y-%m-%d}_')); ws.close()

    def test_gate_labels_can_be_moved(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'A01 sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.resize(1500,900); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); ws.add_gate(plot,[[1,2],[4,2],[4,5],[1,5]]); gate=ws.gates[0]; plot.repaint()
            before=QRectF(plot.label_hits[gate.id]); start=before.center().toPoint(); end=start+QPoint(30,25)
            QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start); QTest.mouseMove(plot,end)
            QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end); plot.repaint()
            after=plot.label_hits[gate.id]; self.assertAlmostEqual(after.left(),before.left()+30,delta=1.5); self.assertAlmostEqual(after.top(),before.top()+25,delta=1.5)
            self.assertEqual(ws.gates[0].vertices,[[1,2],[4,2],[4,5],[1,5]])
            ws.gates[0].vertices=plot.move_gate(ws.gates[0],[1,2],[2,3]); plot.repaint(); moved=plot.label_hits[gate.id]
            self.assertGreater(moved.left(),after.left()); self.assertLess(moved.top(),after.top())
            ws.undo(); plot=ws.active; plot.repaint(); self.assertIsNone(ws.gates[0].label_offset); self.assertAlmostEqual(plot.label_hits[gate.id].left(),before.left(),delta=1)
            with patch.object(ws,'edit_gate') as edit:
                QTest.mouseDClick(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,plot.label_hits[gate.id].center().toPoint()); edit.assert_called_once_with(gate.id)
            ws.add_quadrants(plot,[3.,4.]); plot.repaint(); q1,q2=ws.gates[1],ws.gates[2]; other=QRectF(plot.label_hits[q2.id])
            start=plot.label_hits[q1.id].center().toPoint(); QTest.mousePress(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
            QTest.mouseMove(plot,start+QPoint(0,20)); QTest.mouseRelease(plot,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start+QPoint(0,20)); plot.repaint()
            self.assertIsNotNone(ws.gates[1].label_offset); self.assertIsNone(ws.gates[2].label_offset); self.assertEqual(plot.label_hits[q2.id],other)
            ws.close()

    def test_quadrant_lines_only_group_delete_and_hierarchy_delete(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'A01 sample.fcs'; fixture(source)
            ws=Workspace(); ws.import_paths([str(source)]); ws.resize(1500,900); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); ws.add_gate(plot,[[1.5,2.5],[3.5,2.5],[3.5,4.5],[1.5,4.5]]); box=ws.gates[0].id
            ws.add_quadrants(plot,[2.5,3.5]); quadrants=[g.id for g in ws.gates[1:]]; plot.repaint()
            inside=plot.xy(2.0,3.0); self.assertEqual(plot.gate_at(inside)[0],box)
            on_line=plot.xy(2.5,3.0); self.assertIn(plot.gate_at(on_line)[0],quadrants)
            empty=plot.xy(4.5,5.5); self.assertIsNone(plot.gate_at(empty)[0]); self.assertIn(plot.gate_at(empty,True)[0],quadrants)
            plot.selected=quadrants[1]; plot.setFocus(); QTest.keyClick(plot,Qt.Key.Key_Delete)
            self.assertEqual([g.id for g in ws.gates],[box]); ws.undo(); self.assertEqual(len(ws.gates),5)
            ws.refresh_table(); row=next(r for r in range(ws.table.rowCount()) if ws.table.item(r,0).data(Qt.ItemDataRole.UserRole)==box)
            ws.table.setCurrentCell(row,0); ws.table.setFocus(); QTest.keyClick(ws.table,Qt.Key.Key_Delete)
            self.assertEqual(sorted(g.id for g in ws.gates),sorted(quadrants)); ws.close()

    def test_analysis_export_long_wide_and_auto_named_csv(self):
        import datetime, csv as csvmodule, io
        with tempfile.TemporaryDirectory() as d:
            for name in ('A1 x.fcs','A2 x.fcs','A3 x.fcs'): fixture(Path(d)/name)
            ws=Workspace(); ws.show_workspace(); ws.import_paths([d]); a,b,c=ws.samples; a.condition=b.condition='Ctrl'; c.condition='Drug'; ws.condition_order=['Drug','Ctrl']; ws.refresh()
            ws.parameter.setCurrentIndex(ws.parameter.findData('FSC-A'))
            wide=list(csvmodule.reader(io.StringIO(ws.comparison_csv(layout='wide'))))
            self.assertEqual(wide,[['Drug','Ctrl'],['3.0','3.0'],['','3.0']])
            long=list(csvmodule.reader(io.StringIO(ws.comparison_csv())))
            self.assertEqual(long[0],['Sample','Condition','Population','Metric','Parameter','Value','Population count','Parent count'])
            self.assertEqual([r[1] for r in long[1:]],['Drug','Ctrl','Ctrl']); self.assertEqual(long[1][3:],['Median','FSC-A','3.0','3','3'])
            ws.resize(1500,900); ws.show(); self.app.processEvents(); before=ws.chart.geometry()
            QTest.mouseClick(ws.prism_button,Qt.MouseButton.LeftButton); self.app.processEvents()
            self.assertEqual(QApplication.clipboard().text().splitlines()[0],'Drug\tCtrl'); self.assertEqual(ws.export_note.text(),'✓ Copied'); self.assertIn('Prism',ws.export_note.toolTip())
            self.assertEqual(ws.chart.geometry(),before)
            project=Path(d)/'p.cytose'; ws.project_path=str(project); ws.autosave(); ws.timer.stop(); ws.project_path=str(project)
            expected=f'{datetime.date.today():%Y-%m-%d}_FSC-A_All-Events_wide.csv'
            with patch('cytose.app.QFileDialog.getSaveFileName') as picker:
                first=ws.export_csv('wide'); second=ws.export_csv('wide'); picker.assert_not_called()
            self.assertEqual(first,Path(d)/expected); self.assertEqual(second.name,expected.replace('.csv','_2.csv')); self.assertTrue(first.read_text().startswith('Drug,Ctrl'))
            ws.project_path=None
            with patch('cytose.app.QFileDialog.getSaveFileName',return_value=('','')) as picker: self.assertIsNone(ws.export_csv('long'))
            self.assertTrue(picker.call_args[0][2].endswith('_FSC-A_All-Events_long.csv')); ws.close()

    def test_duplicate_and_new_all_events_plot(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'A01 sample.fcs'; fixture(source)
            ws=Workspace(); ws.resize(1500,900); ws.show_workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            self.assertFalse(ws.plots[0].closable()); ws.add_gate(ws.active,[[0,0],[4,0],[4,5],[0,5]]); ws.open_gate(ws.gates[0].id); gated=ws.plots[1]
            gated.set_axis('x','SSC-A'); ws.duplicate_plot(gated); copy=ws.plots[-1]
            self.assertEqual((copy.population,copy.x,copy.y,copy.grid_slot),(gated.population,'SSC-A',gated.y,2)); self.assertEqual(copy.bounds,gated.bounds)
            ws.add_all_events_plot(); self.assertIsNone(ws.plots[-1].population); self.assertEqual(ws.plots[-1].grid_slot,3)
            ws.undo(); self.assertEqual(len(ws.plots),3); self.assertTrue(ws.plots[0].closable())
            ws.close_plot(ws.plots[0]); self.assertEqual(len(ws.plots),2); ws.close()

    def test_right_click_never_starts_a_gate_or_zoom(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'A01 sample.fcs'; fixture(source)
            ws=Workspace(); ws.resize(1500,900); ws.show_workspace(); ws.import_paths([str(source)]); ws.show(); self.app.processEvents()
            plot=ws.active; plot.reset(); r=plot.plot_rect()
            for mode in ('rectangle','ellipse','zoom'):
                ws.set_mode(mode); QTest.mousePress(plot,Qt.MouseButton.RightButton,pos=r.center().toPoint()); self.assertIsNone(plot.start)
                plot.start=plot.raw(r.center()); QTest.mouseMove(plot,(r.center()+r.topLeft()).toPoint()/2); self.assertIsNone(plot.start)
            self.assertEqual(ws.gates,[]); ws.close()

    def test_compensation_controls_and_correction(self):
        with tempfile.TemporaryDirectory() as d:
            names=['FSC-A','FL1-A','FL2-A']
            for name,rows in (('A1 sample.fcs',[[1,100,30],[2,200,40]]),('B1 FL1 control.fcs',[[1,v,0.1*v] for v in range(100,2100,100)]),('C1 unstained.fcs',[[1,0,0]]*5)):
                multichannel_fixture(Path(d)/name,names,rows)
            ws=Workspace(); ws.show_workspace(); ws.import_paths([d]); ws.resize(1400,900); ws.show(); self.app.processEvents()
            control,unstained=ws.samples[1],ws.samples[2]
            ws.sample_list.setCurrentRow(0); ws.move_to_controls([control.path,unstained.path])
            self.assertEqual([s.name for s in ws.samples],['A1 sample.fcs']); self.assertEqual(len(ws.comparison_rows()),1); self.assertTrue(ws.controls_box.isVisible())
            self.assertEqual(ws.control_stains,{control.path:'FL1',unstained.path:'unstained'})
            from cytose.compensation import CompensationDialog
            dialog=CompensationDialog(ws); self.assertEqual(dialog.channels,['FL1-A','FL2-A']); dialog.from_controls()
            settings,stains=dialog.result(); self.assertTrue(settings['enabled']); self.assertAlmostEqual(settings['matrix'][0][1],0.1,places=3); dialog.close()
            sample=ws.samples[0]; raw=sample.events.copy()
            with patch('cytose.compensation.CompensationDialog.exec',return_value=1), patch('cytose.compensation.CompensationDialog.result',return_value=(settings,stains)): ws.edit_compensation()
            self.assertTrue(ws.compensation_button.isChecked()); np.testing.assert_allclose(sample.events[:,2],raw[:,2]-0.1*raw[:,1],atol=1e-3); np.testing.assert_array_equal(sample.events_raw,raw)
            project=Path(d)/'p.cytose'; ws.project_path=str(project); ws.autosave(); ws.timer.stop(); ws.project_path=None
            restored=Workspace(); restored.load_project(project); self.assertEqual(len(restored.controls),2); self.assertTrue(restored.compensation['enabled'])
            np.testing.assert_allclose(restored.samples[0].events,sample.events,atol=1e-3); restored.timer.stop(); restored.close()
            ws.undo(); self.assertFalse(ws.compensation['enabled']); np.testing.assert_array_equal(ws.samples[0].events,raw); self.assertIsNone(ws.samples[0].raw)
            ws.move_to_samples([control.path]); self.assertEqual(len(ws.samples),2); ws.close()

    def test_compensation_dialog_area_channels_preview_and_choosing_controls(self):
        with tempfile.TemporaryDirectory() as d:
            names=['FSC-A','FL1-A','FL2-A','FL1-H','FL2-H']
            for name in ('A1 s.fcs','B1 FL1.fcs'): multichannel_fixture(Path(d)/name,names,[[1,v,0.2*v,v,0.2*v] for v in range(100,1100,100)])
            ws=Workspace(); ws.show_workspace(); ws.import_paths([d]); ws.show()
            from cytose.compensation import CompensationDialog
            dialog=CompensationDialog(ws); self.assertEqual(dialog.channels,['FL1-A','FL2-A']); self.assertFalse(dialog.calculate.isEnabled())
            self.assertIsNotNone(dialog.preview.values); self.assertEqual(dialog.preview.values.shape,(10,2))
            with patch('cytose.overlay.SampleChooser.exec',return_value=1), patch('cytose.overlay.SampleChooser.paths',return_value=[ws.samples[1].path]): dialog.choose_controls()
            self.assertEqual([c.name for c in ws.controls],['B1 FL1.fcs']); self.assertEqual(dialog.sample.itemData(0),ws.controls[0].path); self.assertEqual(dialog.sample.itemText(0),'B1 FL1.fcs (control)'); dialog.sample.setCurrentIndex(1); self.assertTrue(dialog.calculate.isEnabled())
            box=dialog.stain_boxes[ws.controls[0].path]; self.assertEqual(box.currentData(),'FL1'); self.assertGreaterEqual(box.minimumWidth(),QFontMetricsF(box.font()).horizontalAdvance(box.currentText()))
            bounds=list(dialog.preview.bounds); dialog.from_controls(); dialog.preview.recompute(); self.assertLess(abs(np.median(dialog.preview.values[:,1])),1.0)
            self.assertEqual(dialog.preview.bounds,bounds); self.assertLess(bounds[1][0],0); self.assertIsNotNone(dialog.preview.raw)
            image=dialog.preview.density(np.array([[100.,100.]]),0,1,QColor('#ffffff')); self.assertIsNotNone(image)  # far outside: drawn on the edge
            self.assertGreater(image.pixelColor(47,0).alpha(),0); self.assertFalse(dialog.preview.grab().isNull()); dialog.close(); ws.close()

    def test_old_stacked_overlay_becomes_offset(self):
        ws=Workspace(); ws.overlays=[{'id':'o','name':'Old','kind':'histogram','x':'FSC-A','layout':'stacked','overlap':0.3,'entries':[]}]
        ws.show_overlay('o'); self.assertAlmostEqual(ws.overlays[0]['offset'],0.7); self.assertNotIn('layout',ws.overlays[0]); ws.close()

if __name__=='__main__': unittest.main()
