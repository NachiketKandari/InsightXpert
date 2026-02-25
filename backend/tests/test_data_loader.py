"""Tests for the universal data loader (insightxpert.db.data_loader)."""

import pandas as pd
import pytest
from pathlib import Path
from sqlalchemy import create_engine, text, inspect

from insightxpert.db.data_loader import _read_source, _apply_column_map, load_data

# ---------------------------------------------------------------------------
# Sample CSV content that mirrors real transaction column headers
# ---------------------------------------------------------------------------
SAMPLE_CSV_HEADERS = (
    "Transaction ID,Timestamp,Transaction Type,merchant_category,"
    "Amount (INR),transaction_status,sender_age_group,receiver_age_group,"
    "sender_state,sender_bank,receiver_bank,device_type,network_type,"
    "fraud_flag,hour_of_day,day_of_week,is_weekend"
)

SAMPLE_CSV_ROW = (
    "TXN001,2024-01-15 10:30:00,UPI,Food & Dining,"
    "250.00,Success,26-35,18-25,"
    "Maharashtra,SBI,HDFC,Mobile,4G,"
    "0,10,Monday,0"
)


def _write_csv(path: Path, rows: int = 3) -> Path:
    """Write a small CSV file with transaction-style data and return its path."""
    lines = [SAMPLE_CSV_HEADERS]
    for i in range(1, rows + 1):
        lines.append(
            f"TXN{i:03d},2024-01-{i:02d} 10:30:00,UPI,Food & Dining,"
            f"{100.0 * i},Success,26-35,18-25,"
            f"Maharashtra,SBI,HDFC,Mobile,4G,"
            f"0,10,Monday,0"
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _read_source
# ---------------------------------------------------------------------------

class TestReadSource:
    def test_read_source_csv(self, tmp_path):
        """_read_source should correctly read a CSV file into a DataFrame."""
        csv_path = _write_csv(tmp_path / "data.csv", rows=3)

        df = _read_source(csv_path)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "Transaction ID" in df.columns
        assert "Amount (INR)" in df.columns

    def test_read_source_unsupported(self, tmp_path):
        """_read_source should raise ValueError for unsupported file types."""
        txt_path = tmp_path / "data.txt"
        txt_path.write_text("some text", encoding="utf-8")

        with pytest.raises(ValueError, match="Unsupported file type.*\\.txt"):
            _read_source(txt_path)


# ---------------------------------------------------------------------------
# _apply_column_map
# ---------------------------------------------------------------------------

class TestApplyColumnMap:
    def test_apply_column_map_transactions(self, tmp_path):
        """_apply_column_map should rename CSV headers to DB column names for
        the transactions table."""
        csv_path = _write_csv(tmp_path / "data.csv", rows=1)
        df = _read_source(csv_path)

        result = _apply_column_map(df, "transactions")

        # Mapped columns should now use DB names
        assert "transaction_id" in result.columns
        assert "amount_inr" in result.columns
        assert "transaction_type" in result.columns

        # Original mixed-case/spaced names should be gone
        assert "Transaction ID" not in result.columns
        assert "Amount (INR)" not in result.columns
        assert "Transaction Type" not in result.columns

    def test_apply_column_map_other_table(self, tmp_path):
        """_apply_column_map should leave columns untouched for
        non-transactions tables."""
        csv_path = _write_csv(tmp_path / "data.csv", rows=1)
        df = _read_source(csv_path)
        original_columns = list(df.columns)

        result = _apply_column_map(df, "other_table")

        assert list(result.columns) == original_columns


# ---------------------------------------------------------------------------
# load_data (integration)
# ---------------------------------------------------------------------------

class TestLoadData:
    def _sqlite_url(self, tmp_path: Path) -> str:
        return f"sqlite:///{tmp_path / 'test.db'}"

    def test_load_data_csv_to_sqlite(self, tmp_path):
        """load_data should load CSV rows into a SQLite table and return the
        correct row count."""
        csv_path = _write_csv(tmp_path / "data.csv", rows=5)
        db_url = self._sqlite_url(tmp_path)

        row_count = load_data(
            source=csv_path,
            table="transactions",
            db_url=db_url,
        )

        assert row_count == 5

        # Verify rows actually landed in the database
        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM transactions"))
            assert result.scalar() == 5
        engine.dispose()

    def test_load_data_creates_indexes(self, tmp_path):
        """load_data should create indexes on the transactions table."""
        csv_path = _write_csv(tmp_path / "data.csv", rows=2)
        db_url = self._sqlite_url(tmp_path)

        load_data(source=csv_path, table="transactions", db_url=db_url)

        engine = create_engine(db_url)
        insp = inspect(engine)
        indexes = insp.get_indexes("transactions")
        index_names = {idx["name"] for idx in indexes}

        expected_indexes = {
            "idx_txn_type",
            "idx_status",
            "idx_merchant",
            "idx_sender_bank",
            "idx_device",
            "idx_fraud",
            "idx_hour",
            "idx_weekend",
            "idx_state",
        }
        assert expected_indexes.issubset(index_names), (
            f"Missing indexes: {expected_indexes - index_names}"
        )
        engine.dispose()

    def test_load_data_replace_mode(self, tmp_path):
        """Loading twice with if_exists='replace' should overwrite, not append."""
        csv_path = _write_csv(tmp_path / "data.csv", rows=3)
        db_url = self._sqlite_url(tmp_path)

        load_data(source=csv_path, table="transactions", db_url=db_url, if_exists="replace")
        load_data(source=csv_path, table="transactions", db_url=db_url, if_exists="replace")

        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM transactions"))
            assert result.scalar() == 3, "Replace mode should overwrite, not append"
        engine.dispose()
