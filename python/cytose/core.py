"""FCS data and population calculations, independent of the desktop interface."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import tempfile
import uuid
import weakref
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np


class FCSError(ValueError):
    pass


@dataclass
class Parameter:
    name: str
    stain: str = ''


@dataclass
class Sample:
    path: str
    metadata: dict[str, str]
    parameters: list[Parameter]
    events: np.ndarray
    condition: str = 'Unassigned'
    checksum: str = ''
    raw: np.ndarray | None = None

    @property
    def name(self):
        return Path(self.path).name

    @property
    def events_raw(self):
        """Uncompensated events; `events` holds the compensated values when compensation is on."""
        return self.events if self.raw is None else self.raw


def read_fcs(path: str | Path) -> Sample:
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 58 or data[:6] not in (b'FCS2.0', b'FCS3.0', b'FCS3.1'):
        raise FCSError('Unsupported or invalid FCS header')
    def number(start, end):
        try:
            return int(data[start:end].strip() or b'0')
        except ValueError as exc:
            raise FCSError('Invalid FCS header offset') from exc
    start, end = number(10, 18), number(18, 26)
    if start < 58 or end < start or end >= len(data):
        raise FCSError('Invalid TEXT offsets')
    text = data[start:end + 1]
    delimiter = text[0]
    fields, current, index = [], bytearray(), 1
    while index < len(text):
        char = text[index]
        if char == delimiter:
            if index + 1 < len(text) and text[index + 1] == delimiter:
                current.append(char)
                index += 2
                continue
            fields.append(current.decode('latin-1'))
            current.clear()
        else:
            current.append(char)
        index += 1
    if current:
        fields.append(current.decode('latin-1'))
    if len(fields) % 2:
        raise FCSError('Malformed TEXT key/value pairs')
    meta = {fields[i].upper(): fields[i + 1] for i in range(0, len(fields), 2)}
    try:
        par, total = int(meta['$PAR']), int(meta['$TOT'])
        datatype, order = meta['$DATATYPE'].upper(), meta['$BYTEORD']
        if not 0 < par <= 1024 or total < 0 or meta['$MODE'].upper() != 'L':
            raise FCSError('Only valid list-mode FCS data is supported')
        if meta.get('$NEXTDATA', '0') not in ('', '0'):
            raise FCSError('Multiple datasets in one FCS file are unsupported')
        if order in ('1,2', '1,2,3,4', '1,2,3,4,5,6,7,8'):
            endian = '<'
        elif order in ('2,1', '4,3,2,1', '8,7,6,5,4,3,2,1'):
            endian = '>'
        else:
            raise FCSError(f'Unsupported byte order: {order}')
        names, dtype = [], []
        for i in range(1, par + 1):
            name, bits = meta[f'$P{i}N'], int(meta[f'$P{i}B'])
            if not name:
                raise FCSError('Empty parameter name')
            kind = {'I': 'u', 'F': 'f', 'D': 'f'}.get(datatype)
            if kind is None or (datatype == 'I' and bits not in (8, 16, 32, 64)) or (datatype == 'F' and bits != 32) or (datatype == 'D' and bits != 64):
                raise FCSError(f'Unsupported data type/width: {datatype}/{bits}')
            names.append(Parameter(name, meta.get(f'$P{i}S', '')))
            dtype.append((f'p{i}', f'{endian}{kind}{bits // 8}'))
        start = number(26, 34) or int(meta.get('$BEGINDATA', '-1'))
        end = number(34, 42) or int(meta.get('$ENDDATA', '-1'))
        rowtype = np.dtype(dtype)
        if start < 0 or end < start - 1 or end >= len(data) or start + total * rowtype.itemsize > end + 1:
            raise FCSError('DATA segment is truncated or offsets are invalid')
        rows = np.frombuffer(data, dtype=rowtype, count=total, offset=start)
        events = np.column_stack([rows[f'p{i}'] for i in range(1, par + 1)]).astype(np.float64)
        events.flags.writeable = False
        return Sample(str(path.resolve()), meta, names, events, checksum=hashlib.sha256(data).hexdigest())
    except (KeyError, ValueError, OverflowError) as exc:
        if isinstance(exc, FCSError):
            raise
        raise FCSError(f'Malformed or incomplete FCS metadata: {exc}') from exc


@dataclass
class Gate:
    name: str
    x: str
    y: str
    vertices: list[list[float]]
    parent: str | None = None
    color: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    quadrant: list | None = None
    quadrant_group: str | None = None
    shape: str | None = None
    spokes: list | None = None
    label_offset: list | None = None


def log_scale(name):
    """Fluorescence channels are displayed on a log scale; widths and other channels are linear."""
    name=name.strip().upper()
    return bool(re.match(r'^FL-?[1-4](?!\d)',name)) and not re.search(r'(?:[-_ ]W|WIDTH)$',name)


SPOKE_DEFAULTS = (math.pi/2, 0., -math.pi/2, math.pi)  # top, right, bottom, left


def quadrant_mask(gate, x, y):
    """Events in one quadrant. Without moved spokes the lines are straight; otherwise each
    quadrant is the wedge between two neighbouring spokes, on the displayed (log/linear) axes."""
    tx, ty, hx, hy = gate.quadrant[:4]
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if not gate.spokes:
        return (x > tx if hx else x <= tx) & (y > ty if hy else y <= ty)
    lx, ly = log_scale(gate.x), log_scale(gate.y); cx, cy = float(transform(tx, lx)), float(transform(ty, ly))
    angles = []
    for (ax, ay), default in zip(gate.spokes, SPOKE_DEFAULTS):
        dx, dy = float(transform(ax, lx))-cx, float(transform(ay, ly))-cy
        angles.append(math.atan2(dy, dx) if dx or dy else default)
    top, right, bottom, left = angles
    start, end = {(True, True): (right, top), (False, True): (top, left), (False, False): (left, bottom), (True, False): (bottom, right)}[(bool(hx), bool(hy))]
    with np.errstate(invalid='ignore'):
        angle = np.arctan2(transform(y, ly)-cy, transform(x, lx)-cx)
    return np.mod(angle-start, 2*math.pi) < np.mod(end-start, 2*math.pi)


_MASKS = OrderedDict()
_MASK_LIMIT = 64


def membership(sample: Sample, gates: list[Gate], gate_id: str | None) -> np.ndarray:
    """Read-only event mask for a population, cached per sample and full gate definition.

    Each gate reuses its parent's cached mask, so redraws, statistics and backgating
    share work. Keys include every ancestor's geometry, so edits never reuse stale masks.
    """
    if gate_id is None:
        return _cached(sample, ('all',), lambda: np.ones(len(sample.events), dtype=bool))
    signature = population_signature(gates, gate_id)
    return _cached(sample, signature, lambda: _compute_membership(sample, gates, gate_id, signature))


def _cached(sample, signature, compute):
    key = (id(sample.events), tuple(p.name for p in sample.parameters), signature)
    entry = _MASKS.pop(key, None)
    if entry is None or entry[0]() is not sample.events:
        mask = compute(); mask.flags.writeable = False
        entry = (weakref.ref(sample.events), mask)
    _MASKS[key] = entry
    if len(_MASKS) > _MASK_LIMIT: _MASKS.popitem(last=False)
    return entry[1]


def _compute_membership(sample, gates, gate_id, signature):
    total = len(sample.events)
    if any(item[0] == 'invalid' for item in signature):
        return np.zeros(total, dtype=bool)
    gate = next(g for g in gates if g.id == gate_id)
    names = [p.name for p in sample.parameters]
    if names.count(gate.x) != 1 or names.count(gate.y) != 1:
        return np.zeros(total, dtype=bool)
    parent = membership(sample, gates, gate.parent)
    x, y = sample.events[:, names.index(gate.x)], sample.events[:, names.index(gate.y)]
    if gate.quadrant is not None:
        return parent & quadrant_mask(gate, x, y) & np.isfinite(x) & np.isfinite(y)
    verts = gate.vertices
    if len(verts) < 3:
        return np.zeros(total, dtype=bool)
    # Only events in the parent and the gate's bounding box need the polygon test.
    xs, ys = [v[0] for v in verts], [v[1] for v in verts]
    candidates = np.flatnonzero(parent & (x >= min(xs)) & (x <= max(xs)) & (y >= min(ys)) & (y <= max(ys)))
    cx, cy = x[candidates], y[candidates]
    inside = np.zeros(len(candidates), dtype=bool); boundary = np.zeros(len(candidates), dtype=bool)
    for a, b in zip(verts, verts[-1:] + verts[:-1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        cross = (cx-a[0])*dy - (cy-a[1])*dx
        boundary |= (np.abs(cross) <= 1e-10 * max(1, abs(dx), abs(dy))) & (cx >= min(a[0], b[0])) & (cx <= max(a[0], b[0])) & (cy >= min(a[1], b[1])) & (cy <= max(a[1], b[1]))
        if dy:
            inside ^= ((a[1] > cy) != (b[1] > cy)) & (cx < dx * (cy-a[1])/dy + a[0])
    mask = np.zeros(total, dtype=bool); mask[candidates[inside | boundary]] = True
    return mask


def population_available(sample: Sample, gates: list[Gate], gate_id: str | None) -> bool:
    """A population cannot be quantified when an axis is absent or ambiguous."""
    by_id = {gate.id: gate for gate in gates}
    names = [parameter.name for parameter in sample.parameters]
    seen = set()
    while gate_id is not None:
        if gate_id in seen or gate_id not in by_id:
            return False
        seen.add(gate_id)
        gate = by_id[gate_id]
        if names.count(gate.x) != 1 or names.count(gate.y) != 1:
            return False
        gate_id = gate.parent
    return True


def population_signature(gates: list[Gate], gate_id: str | None):
    """Return the membership-relevant definition of a population and its ancestors."""
    by_id={gate.id:gate for gate in gates}; seen=set(); chain=[]
    while gate_id is not None:
        if gate_id in seen or gate_id not in by_id:
            chain.append(('invalid',gate_id)); break
        seen.add(gate_id); gate=by_id[gate_id]
        chain.append((gate.id,gate.parent,gate.x,gate.y,tuple(map(tuple,gate.vertices)),tuple(gate.quadrant or ()),tuple(map(tuple,gate.spokes or ()))))
        gate_id=gate.parent
    return tuple(chain)


def statistics(sample: Sample, gates: list[Gate], gate_id: str | None, parameter: str):
    if not population_available(sample, gates, gate_id):
        return {'count': None, 'parent': None, 'total': len(sample.events),
                'percent_parent': None, 'percent_total': None, 'mean': None, 'median': None}
    mask = membership(sample, gates, gate_id)
    gate = next((g for g in gates if g.id == gate_id), None)
    parent = membership(sample, gates, gate.parent if gate else None).sum()
    count, total = int(mask.sum()), len(mask)
    names = [p.name for p in sample.parameters]
    values = sample.events[mask, names.index(parameter)] if names.count(parameter) == 1 else np.array([])
    values = values[np.isfinite(values)]
    return {'count': count, 'parent': int(parent), 'total': total,
            'percent_parent': 100*count/parent if parent else None,
            'percent_total': 100*count/total if total else None,
            'mean': float(np.mean(values)) if len(values) else None,
            'median': float(np.median(values)) if len(values) else None}


class StatisticsCache:
    """Bounded cache of scalar statistics; does not retain samples or event arrays."""
    def __init__(self, capacity=2048, calculator=None):
        self.capacity=capacity; self.calculator=calculator or statistics; self.entries=OrderedDict()

    def get(self, sample: Sample, gates: list[Gate], gate_id: str | None, parameter: str):
        key=(id(sample),id(sample.events),tuple(p.name for p in sample.parameters),
             population_signature(gates,gate_id),parameter)
        entry=self.entries.pop(key,None)
        if entry is not None and entry[0]() is sample and entry[1]() is sample.events:
            self.entries[key]=entry; return entry[2]
        result=self.calculator(sample,gates,gate_id,parameter)
        self.entries[key]=(weakref.ref(sample),weakref.ref(sample.events),result)
        if len(self.entries)>self.capacity: self.entries.popitem(last=False)
        return result


def condition_name(name: str) -> str:
    stem=Path(name).stem.strip()
    return re.sub(r'^[A-Za-z]{1,2}(?:0{0,2}[1-9]|0?[1-3][0-9]|0?4[0-8])[\s_-]+', '', stem).strip() or stem


SCATTER_GATE_NAME = 'Cells'


def default_gate_name(x: str, y: str, existing) -> str:
    """Cells for forward vs side scatter, Singlets for height/area/width of one scatter channel, else G1, G2, ..."""
    base=lambda name: re.sub(r'[-_ ]?[AHW]$','',name.strip().upper())
    existing=set(existing)
    if base(x)==base(y) and base(x) in ('FSC','SSC') and x!=y: name=f'Singlets'
    elif {base(x),base(y)}=={'FSC','SSC'}: name=SCATTER_GATE_NAME
    else:
        number=1
        while f'G{number}' in existing: number+=1
        return f'G{number}'
    if name not in existing: return name
    number=2
    while f'{name} {number}' in existing: number+=1
    return f'{name} {number}'


def natural_key(name: str):
    """Sort key that orders embedded numbers by value, so A2 comes before A10."""
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r'(\d+)', name)]


def export_csv(rows, delimiter=','):
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=delimiter, lineterminator='\n')
    writer.writerows(rows)
    return output.getvalue()


def save_json(path, document):
    """Atomic replacement: never overwrite the last valid project with partial JSON."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.cytose-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            json.dump(document, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def transform(values, logarithmic):
    values = np.asarray(values, dtype=float)
    return np.sign(values) * np.log10(1 + np.abs(values)) if logarithmic else values


def inverse(values, logarithmic):
    values = np.asarray(values, dtype=float)
    return np.sign(values) * (np.power(10, np.abs(values)) - 1) if logarithmic else values


# --- Compensation -----------------------------------------------------------
_SCATTER = re.compile(r'^(FSC|SSC|TIME|WIDTH|EVENT)', re.IGNORECASE)


def fluorescence_channels(samples) -> list[str]:
    """Fluorescence detectors shared by the samples, in file order (scatter, time and width excluded)."""
    names = [p.name for p in samples[0].parameters] if samples else []
    return [name for name in names if not _SCATTER.match(name) and all(name in [p.name for p in s.parameters] for s in samples)]


def compensation_channels(samples) -> list[str]:
    """Area (-A) fluorescence detectors; compensation is defined on area values only."""
    channels = fluorescence_channels(samples)
    area = [name for name in channels if re.search(r'[-_ ]A$', name.strip())]
    return area or channels


def fluor_base(name: str) -> str:
    """Detector without its area/height/width suffix: FL1-A and FL1-H share 'FL1'."""
    return re.sub(r'[-_ ]?[AHW]$', '', name.strip())


def spillover_from_metadata(metadata) -> tuple[list[str], np.ndarray] | None:
    """Parse $SPILLOVER/SPILL ('n,name1..namen,values row by row'); rows spill into columns."""
    text = next((metadata[key] for key in ('$SPILLOVER', 'SPILL', '$SPILL', 'SPILLOVER') if metadata.get(key)), None)
    if not text: return None
    try:
        parts = [part.strip() for part in text.split(',')]; n = int(parts[0])
        names = parts[1:1+n]; values = np.array([float(v) for v in parts[1+n:1+n+n*n]]).reshape(n, n)
    except (ValueError, IndexError):
        return None
    return names, values


def spillover_from_controls(controls, stains, channels) -> np.ndarray:
    """Estimate spillover from single-stained controls (identity where unknown).

    For a control stained in detector base b, the spillover from b into channel j (same
    area/height block) is the ratio of background-subtracted medians of the brightest 10% of
    events in b. Background is the unstained control's median, or the dimmest 30% of the same
    control when there is none. Controls are not gated first, so results are approximate.
    """
    index = {name: i for i, name in enumerate(channels)}; matrix = np.eye(len(channels))
    unstained = next((c for c in controls if stains.get(c.path) == 'unstained'), None)
    def column(sample, name):
        names = [p.name for p in sample.parameters]
        return sample.events_raw[:, names.index(name)] if name in names else None
    for control in controls:
        base = stains.get(control.path)
        if not base or base == 'unstained': continue
        for primary in (name for name in channels if fluor_base(name) == base):
            suffix = primary[len(base):]; values = column(control, primary)
            if values is None: continue
            finite = np.isfinite(values)
            bright = finite & (values >= np.percentile(values[finite], 90)) if finite.any() else finite
            dim = finite & (values <= np.percentile(values[finite], 30)) if finite.any() else finite
            def background(name):
                if unstained is not None and column(unstained, name) is not None:
                    reference = column(unstained, name); return float(np.median(reference[np.isfinite(reference)]))
                return float(np.median(column(control, name)[dim]))
            signal = float(np.median(values[bright])) - background(primary)
            if signal <= 0: continue
            for name in channels:
                if name == primary or name[len(fluor_base(name)):] != suffix: continue
                other = column(control, name)
                spill = (float(np.median(other[bright])) - background(name)) / signal
                matrix[index[primary], index[name]] = max(0., spill)
    return matrix


def compensate(sample: 'Sample', channels, matrix) -> np.ndarray:
    """Compensated copy of the sample's raw events: raw[:, channels] x inverse(spillover)."""
    raw = sample.events_raw; names = [p.name for p in sample.parameters]
    if not channels or any(names.count(name) != 1 for name in channels): return raw
    columns = [names.index(name) for name in channels]; events = raw.copy()
    events[:, columns] = raw[:, columns] @ np.linalg.inv(np.asarray(matrix, dtype=float))
    events.flags.writeable = False
    return events
