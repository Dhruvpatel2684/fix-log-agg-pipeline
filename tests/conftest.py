"""Shared test fixtures and configuration."""
import sys
import json
import shutil
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENV_DIR = ROOT / "environment"
SRC_DIR = ENV_DIR / "src"
FIXTURES_DIR = ENV_DIR / "fixtures"

sys.path.insert(0, str(ENV_DIR))

from src.models import LogEntry, WALSegment, Checkpoint, CompactedOutput
from src.wal_reader import WALReader
from src.dedup_engine import DedupEngine
from src.merger import SegmentMerger
from src.temporal_index import TemporalIndex
from src.compactor import IncrementalCompactor
from src.recovery import RecoveryManager


@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture
def segments_dir(fixtures_dir):
    return fixtures_dir / "segments"


@pytest.fixture
def fresh_segments_dir(fixtures_dir):
    return fixtures_dir / "segments_fresh"


@pytest.fixture
def checkpoint_dir(fixtures_dir, tmp_path):
    """Copy checkpoint fixtures to temp dir so tests don't corrupt originals."""
    src = fixtures_dir / "checkpoints"
    dst = tmp_path / "cp_fixture"
    shutil.copytree(src, dst)
    return dst


@pytest.fixture
def tmp_output_dir(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    return out


@pytest.fixture
def tmp_checkpoint_dir(tmp_path):
    cp = tmp_path / "checkpoints"
    cp.mkdir()
    return cp


@pytest.fixture
def loaded_segments(segments_dir):
    reader = WALReader(segments_dir)
    return reader.load_all_segments()


@pytest.fixture
def fresh_segments(fresh_segments_dir):
    reader = WALReader(fresh_segments_dir)
    return reader.load_all_segments()
