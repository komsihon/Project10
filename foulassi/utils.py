# -*- coding: utf-8 -*-


def set_counters(tracker_object, i=0):
    history_fields = [field for field in tracker_object.__dict__.keys() if field.endswith('_history')]
    for name in history_fields:
        field = tracker_object.__dict__[name]
        while len(field) < i + 1:
            field.append(0)
