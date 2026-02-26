"""Tests for dataset CRUD, seeding, and service layer."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from insightxpert.auth.models import (
    Base as AuthBase,
    Dataset,
    DatasetColumn,
    ExampleQuery,
    _uuid,
    _utcnow,
)
from insightxpert.datasets.service import DatasetService


from sqlalchemy import event as sa_event


@pytest.fixture()
def ds_engine():
    """In-memory engine with all auth tables including dataset tables."""
    engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign key enforcement for SQLite
    @sa_event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    AuthBase.metadata.create_all(engine)
    return engine


@pytest.fixture()
def ds_service(ds_engine):
    return DatasetService(ds_engine)


@pytest.fixture()
def seeded_dataset(ds_engine):
    """Seed a test dataset with columns and example queries."""
    now = _utcnow()
    dataset_id = _uuid()

    with Session(ds_engine) as session:
        ds = Dataset(
            id=dataset_id,
            name="test_transactions",
            description="Test dataset",
            ddl="CREATE TABLE test_transactions (id TEXT PRIMARY KEY, amount REAL);",
            documentation="Test documentation for transactions.",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(ds)

        session.add(DatasetColumn(
            id=_uuid(),
            dataset_id=dataset_id,
            column_name="id",
            column_type="TEXT",
            description="Unique identifier",
            ordinal_position=0,
            created_at=now,
        ))
        session.add(DatasetColumn(
            id=_uuid(),
            dataset_id=dataset_id,
            column_name="amount",
            column_type="REAL",
            description="Transaction amount",
            domain_values=None,
            domain_rules="Must be positive",
            ordinal_position=1,
            created_at=now,
        ))

        session.add(ExampleQuery(
            id=_uuid(),
            dataset_id=dataset_id,
            question="What is the total amount?",
            sql="SELECT SUM(amount) FROM test_transactions;",
            category="Descriptive",
            is_active=True,
            created_at=now,
        ))

        session.commit()

    return dataset_id


class TestDatasetModels:
    """Test that SQLAlchemy models create and query correctly."""

    def test_create_dataset(self, ds_engine):
        now = _utcnow()
        with Session(ds_engine) as session:
            ds = Dataset(
                id=_uuid(),
                name="my_dataset",
                ddl="CREATE TABLE t (id INT);",
                documentation="Docs here",
                created_at=now,
                updated_at=now,
            )
            session.add(ds)
            session.commit()

            result = session.query(Dataset).filter_by(name="my_dataset").first()
            assert result is not None
            assert result.ddl == "CREATE TABLE t (id INT);"
            assert result.is_active is True

    def test_dataset_columns_cascade_on_delete(self, ds_engine, seeded_dataset):
        """Deleting a dataset should cascade-delete its columns."""
        with Session(ds_engine) as session:
            ds = session.get(Dataset, seeded_dataset)
            session.delete(ds)
            session.commit()

            cols = session.query(DatasetColumn).filter_by(dataset_id=seeded_dataset).all()
            assert len(cols) == 0

    def test_example_queries_cascade_on_delete(self, ds_engine, seeded_dataset):
        """Deleting a dataset should cascade-delete its example queries."""
        with Session(ds_engine) as session:
            ds = session.get(Dataset, seeded_dataset)
            session.delete(ds)
            session.commit()

            queries = session.query(ExampleQuery).filter_by(dataset_id=seeded_dataset).all()
            assert len(queries) == 0


class TestDatasetService:
    """Test the DatasetService layer."""

    def test_get_active_dataset(self, ds_service, seeded_dataset):
        active = ds_service.get_active_dataset()
        assert active is not None
        assert active["name"] == "test_transactions"
        assert active["is_active"] is True

    def test_get_active_dataset_none(self, ds_service):
        """No datasets -> None."""
        assert ds_service.get_active_dataset() is None

    def test_list_datasets(self, ds_service, seeded_dataset):
        datasets = ds_service.list_datasets()
        assert len(datasets) == 1
        assert datasets[0]["name"] == "test_transactions"

    def test_get_dataset_by_id(self, ds_service, seeded_dataset):
        ds = ds_service.get_dataset_by_id(seeded_dataset)
        assert ds is not None
        assert ds["id"] == seeded_dataset

    def test_get_dataset_columns(self, ds_service, seeded_dataset):
        cols = ds_service.get_dataset_columns(seeded_dataset)
        assert len(cols) == 2
        assert cols[0]["column_name"] == "id"
        assert cols[1]["column_name"] == "amount"

    def test_get_example_queries(self, ds_service, seeded_dataset):
        queries = ds_service.get_example_queries(seeded_dataset)
        assert len(queries) == 1
        assert "total amount" in queries[0]["question"]

    def test_build_documentation_markdown(self, ds_service, seeded_dataset):
        md = ds_service.build_documentation_markdown(seeded_dataset)
        assert "Column Details" in md
        assert "amount" in md
        assert "Must be positive" in md

    def test_update_dataset(self, ds_service, seeded_dataset):
        updated = ds_service.update_dataset(seeded_dataset, description="Updated desc")
        assert updated is not None
        assert updated["description"] == "Updated desc"

    def test_activate_dataset(self, ds_engine, ds_service, seeded_dataset):
        # Create a second dataset
        now = _utcnow()
        second_id = _uuid()
        with Session(ds_engine) as session:
            session.add(Dataset(
                id=second_id,
                name="second_ds",
                ddl="CREATE TABLE t2 (x INT);",
                documentation="Second dataset",
                is_active=False,
                created_at=now,
                updated_at=now,
            ))
            session.commit()

        # Activate the second dataset
        ok = ds_service.activate_dataset(second_id)
        assert ok is True

        # First should be deactivated
        first = ds_service.get_dataset_by_id(seeded_dataset)
        assert first["is_active"] is False

        second = ds_service.get_dataset_by_id(second_id)
        assert second["is_active"] is True

    def test_add_and_delete_example_query(self, ds_service, seeded_dataset):
        result = ds_service.add_example_query(
            seeded_dataset,
            question="How many rows?",
            sql="SELECT COUNT(*) FROM test_transactions;",
            category="Descriptive",
        )
        assert result is not None
        assert result["question"] == "How many rows?"

        queries = ds_service.get_example_queries(seeded_dataset)
        assert len(queries) == 2

        deleted = ds_service.delete_example_query(result["id"])
        assert deleted is True

        queries = ds_service.get_example_queries(seeded_dataset)
        assert len(queries) == 1

    def test_add_and_update_column(self, ds_service, seeded_dataset):
        col = ds_service.add_column(
            seeded_dataset,
            column_name="status",
            column_type="TEXT",
            description="Transaction status",
            ordinal_position=2,
        )
        assert col is not None
        assert col["column_name"] == "status"

        updated = ds_service.update_column(col["id"], description="Updated status desc")
        assert updated is not None
        assert updated["description"] == "Updated status desc"


class TestSeedDatasets:
    """Test the _seed_datasets function from main.py."""

    def test_seed_creates_dataset(self, ds_engine):
        from insightxpert.main import _seed_datasets

        _seed_datasets(ds_engine)

        with Session(ds_engine) as session:
            datasets = session.query(Dataset).all()
            assert len(datasets) == 1
            assert datasets[0].name == "transactions"
            assert datasets[0].is_active is True

            cols = session.query(DatasetColumn).filter_by(dataset_id=datasets[0].id).all()
            assert len(cols) == 17  # 17 columns in the transactions table

            queries = session.query(ExampleQuery).filter_by(dataset_id=datasets[0].id).all()
            assert len(queries) == 12  # 12 example queries

    def test_seed_is_idempotent(self, ds_engine):
        from insightxpert.main import _seed_datasets

        _seed_datasets(ds_engine)
        _seed_datasets(ds_engine)  # Second call should be a no-op

        with Session(ds_engine) as session:
            datasets = session.query(Dataset).all()
            assert len(datasets) == 1


class TestTrainerFromDataset:
    """Test that the Trainer can load from DB datasets."""

    def test_train_from_dataset(self, ds_service, seeded_dataset, rag_store):
        from insightxpert.training.trainer import Trainer

        trainer = Trainer(rag_store)
        count = trainer.train_from_dataset(ds_service)
        # 1 DDL + 1 documentation + 1 Q&A pair = 3
        assert count == 3

    def test_train_from_dataset_no_active(self, ds_service, rag_store):
        from insightxpert.training.trainer import Trainer

        trainer = Trainer(rag_store)
        count = trainer.train_from_dataset(ds_service)
        assert count == 0

    def test_train_insightxpert_with_dataset_service(self, ds_service, seeded_dataset, rag_store):
        from insightxpert.training.trainer import Trainer

        trainer = Trainer(rag_store)
        count = trainer.train_insightxpert(db=None, dataset_service=ds_service)
        # Should load from DB: 1 DDL + 1 doc + 1 Q&A = 3
        assert count == 3

    def test_train_insightxpert_fallback_without_dataset(self, rag_store):
        """Without dataset_service, should fall back to hardcoded data."""
        from insightxpert.training.trainer import Trainer

        trainer = Trainer(rag_store)
        count = trainer.train_insightxpert(db=None, dataset_service=None)
        # 1 DDL + 1 doc + 12 Q&A = 14
        assert count == 14
