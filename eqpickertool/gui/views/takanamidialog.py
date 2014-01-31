# encoding: utf-8
'''
@author:     Jose Emilio Romero Lopez

@copyright:  2013 organization_name. All rights reserved.

@license:    LGPL

@contact:    jemromerol@gmail.com

  This file is part of AMPAPicker.

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU Lesser General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU Lesser General Public License for more details.

  You should have received a copy of the GNU Lesser General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

from PySide import QtCore
from PySide import QtGui
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from eqpickertool.gui.views import navigationtoolbar
from eqpickertool.gui.views import processingdialog
import matplotlib.pyplot as plt
import numpy as np
from eqpickertool.picking import record as rc
from eqpickertool.picking import takanami
from eqpickertool._version import _application_name
from eqpickertool._version import _organization

MINIMUM_MARGIN_IN_SECS = 0.5


class TakanamiTask(QtCore.QObject):
    """A class to handle a Takanami exec. task.

    Attributes:
        record: An opened seismic record.
        start: Start point of the signal segment where
            the algorithm is going to be applied.
        end: End point of the signal segment where
            the algorithm is going to be applied.

    Signals:
        finished: Task finishes.
        position_estimated: Return values of Takanami method are ready.
    """

    finished = QtCore.Signal()
    position_estimated = QtCore.Signal(int, np.ndarray, int)

    def __init__(self, record, start, end):
        super(TakanamiTask, self).__init__()
        self.record = record
        self.start = start
        self.end = end
        self.algorithm = takanami.Takanami()
        self._abort = False

    def run(self):
        self._abort = False
        start_time_in_secs = max(0.0, self.start) / self.record.fs
        end_time_in_secs = (min(len(self.record.signal), self.end) /
                            self.record.fs)
        if self._abort:  # checkpoint
            return
        et, aic, n0_aic = self.algorithm.run(self.record.signal,
                                             self.record.fs,
                                             start_time_in_secs,
                                             end_time_in_secs)
        if self._abort:  # checkpoint
            return
        self.position_estimated.emit(et, aic, n0_aic)
        self.finished.emit()

    def abort(self):
        self._abort = True


class TakanamiDialog(QtGui.QDialog):
    """A dialog to apply Takanami's AR picking method to a selected piece of a
    seismic signal.

    Attributes:
        document: Current opened document containing a seismic record.
        seismic_event: A seismic event to be refined by using Takanami method.
            If no event is provided, then a new seismic event will be created
            by using the estimated arrival time after clicking on 'Accept'
    """

    def __init__(self, document, t_start, t_end, seismic_event=None, parent=None):
        super(TakanamiDialog, self).__init__(parent)

        self.document = document
        self.record = self.document.record

        self._start = int(t_start * self.record.fs)
        self._end = int(t_end * self.record.fs)
        if not 0 <= self._start < len(self.record.signal):
            raise ValueError("Invalid t_start value")
        if not 0 <= self._end < len(self.record.signal):
            raise ValueError("Invalid t_end value")
        if (self._end - self._start) < (MINIMUM_MARGIN_IN_SECS * self.record.fs):
            raise ValueError("Distance between t_start and t_end must be"
                             " at least of %g seconds" % MINIMUM_MARGIN_IN_SECS)

        self.seismic_event = seismic_event
        if self.seismic_event is None:
            self.event_time = self._start + int((self._end - self._start) / 2)
        else:
            self.event_time = self.seismic_event.time
        if not self._start < self.event_time < self._end:
            raise ValueError("Event time must be a value between t-start and t_end")

        self._init_ui()
        self.load_settings()

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.clicked.connect(self.on_click)
        self.start_point_spinbox.timeChanged.connect(self.on_start_point_changed)
        self.end_point_spinbox.timeChanged.connect(self.on_end_point_changed)

        self._task = TakanamiTask(self.record, self._start, self._end)
        self._task.position_estimated.connect(self.on_position_estimated)

        self.wait_dialog = processingdialog.ProcessingDialog(label_text="Applying Takanami's AR method...")
        self.wait_dialog.setWindowTitle("Event detection")

        self.wait_dialog.run(self._task)

    def _init_ui(self):
        self.setWindowTitle("Takanami's Autoregressive Method")
        self.fig, _ = plt.subplots(2, 1, sharex=True)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setMinimumSize(self.canvas.size())
        self.toolBarNavigation = navigationtoolbar.NavigationToolBar(self.canvas, self)
        self.position_label = QtGui.QLabel("Estimated Arrival Time: 00 h 00 m 00.000 s")
        self.group_box = QtGui.QGroupBox(self)
        self.group_box.setTitle("Limits")
        self.start_point_label = QtGui.QLabel("Start point:")
        self.start_point_label.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Policy.Maximum,
                                                               QtGui.QSizePolicy.Policy.Preferred))
        self.start_point_spinbox = QtGui.QTimeEdit(self.group_box)
        self.start_point_spinbox.setDisplayFormat("hh 'h' mm 'm' ss.zzz 's'")
        self.end_point_label = QtGui.QLabel("End point:")
        self.end_point_label.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Policy.Maximum,
                                                               QtGui.QSizePolicy.Policy.Preferred))
        self.end_point_spinbox = QtGui.QTimeEdit(self.group_box)
        self.end_point_spinbox.setDisplayFormat("hh 'h' mm 'm' ss.zzz 's'")
        self.group_box_layout = QtGui.QHBoxLayout(self.group_box)
        self.group_box_layout.setContentsMargins(9, 9, 9, 9)
        self.group_box_layout.setSpacing(12)
        self.group_box_layout.addWidget(self.start_point_label)
        self.group_box_layout.addWidget(self.start_point_spinbox)
        self.group_box_layout.addWidget(self.end_point_label)
        self.group_box_layout.addWidget(self.end_point_spinbox)
        self.button_box = QtGui.QDialogButtonBox(self)
        self.button_box.setOrientation(QtCore.Qt.Horizontal)
        self.button_box.setStandardButtons(QtGui.QDialogButtonBox.Apply |
                                           QtGui.QDialogButtonBox.Cancel |
                                           QtGui.QDialogButtonBox.Ok)
        self.layout = QtGui.QVBoxLayout(self)
        self.layout.setContentsMargins(9, 9, 9, 9)
        self.layout.setSpacing(6)
        self.layout.addWidget(self.toolBarNavigation)
        self.layout.addWidget(self.canvas)
        self.layout.addWidget(self.position_label)
        self.layout.addWidget(self.group_box)
        self.layout.addWidget(self.button_box)

        # set spinboxes's initial values and limits
        time_in_msecs = int((len(self.record.signal) * 1000.0) /
                         self.record.fs)
        self.start_point_spinbox.setTime(QtCore.QTime().addMSecs(0))
        self.end_point_spinbox.setTime(QtCore.QTime().addMSecs(time_in_msecs))
        self.start_point_spinbox.setMinimumTime(QtCore.QTime().addMSecs(0))
        self.end_point_spinbox.setMinimumTime(QtCore.QTime().addMSecs(MINIMUM_MARGIN_IN_SECS * 1000))
        self.start_point_spinbox.setMaximumTime(QtCore.QTime().addMSecs(time_in_msecs - MINIMUM_MARGIN_IN_SECS * 1000))
        self.end_point_spinbox.setMaximumTime(QtCore.QTime().addMSecs(time_in_msecs))

    def on_click(self, button):
        if self.button_box.standardButton(button) == QtGui.QDialogButtonBox.Ok:
            self.save_event()
        if self.button_box.standardButton(button) == QtGui.QDialogButtonBox.Apply:
            self._task = TakanamiTask(self.record, self._start, self._end)
            self._task.position_estimated.connect(self.on_position_estimated)
            self.wait_dialog.run(self._task)

    def on_start_point_changed(self, value):
        time_in_msecs = QtCore.QTime().msecsTo(value)
        t_start = int(max(0, (time_in_msecs / 1000.0) *
                          self.record.fs))
        if self._start != t_start:
            self._start = t_start
            self.end_point_spinbox.setMinimumTime(QtCore.QTime().
                                                  addMSecs(time_in_msecs + MINIMUM_MARGIN_IN_SECS * 1000))

    def on_end_point_changed(self, value):
        time_in_msecs = QtCore.QTime().msecsTo(value)
        t_end = int(min(len(self.record.signal),
                        ((time_in_msecs / 1000.0) *
                         self.record.fs)))
        if self._end != t_end:
            self._end = t_end
            self.start_point_spinbox.setMaximumTime(QtCore.QTime().
                                                    addMSecs(time_in_msecs - MINIMUM_MARGIN_IN_SECS * 1000))

    def on_position_estimated(self, time, aic, n0_aic):
        self.event_time = time
        time_in_msecs = QtCore.QTime().addMSecs((self.event_time * 1000.0) /
                                                self.record.fs)
        self.position_label.setText("Estimated Arrival Time: %s" % time_in_msecs.toString("hh 'h' mm 'm' ss.zzz 's'"))
        # Plot estimated arrival time
        m_event = rc.Event(self.record, time, aic=aic, n0_aic=n0_aic)
        m_event.plot_aic(show_envelope=True, num=self.fig.number)
        self.fig.canvas.draw_idle()

    def load_settings(self):
        """Loads settings from persistent storage."""
        settings = QtCore.QSettings(_organization, _application_name)
        settings.beginGroup("takanami_settings")
        default_margin = int(float(settings.value('takanami_margin', 5.0)) *
                             self.record.fs)
        settings.endGroup()
        self.set_margin(default_margin)

    def save_event(self):
        """"""
        if self.seismic_event is not None:
            if self.seismic_event.time != self.event_time:
                self.document.editEvent(self.seismic_event,
                                        time=self.event_time,
                                        method=rc.method_takanami,
                                        mode=rc.mode_automatic,
                                        status=rc.status_reported)
        else:
            self.document.createEvent(self.event_time,
                                      method=rc.method_takanami,
                                      mode=rc.mode_automatic,
                                      status=rc.status_reported)

    def set_margin(self, margin):
        if margin <= 0:
            raise ValueError("margin must be a positive value")

        margin = max(MINIMUM_MARGIN_IN_SECS * self.record.fs, margin)
        self._start = max(0, self.event_time - margin)
        self._end = min(len(self.record.signal),
                        self.event_time + margin)
        self.start_point_spinbox.setTime(QtCore.QTime().
                                         addMSecs((self._start * 1000.0) /
                                                  self.record.fs))
        self.end_point_spinbox.setTime(QtCore.QTime().
                                       addMSecs((self._end * 1000.0) /
                                                self.record.fs))















