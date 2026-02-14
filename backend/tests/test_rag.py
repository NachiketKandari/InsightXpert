from insightxpert.rag.store import VectorStore


def test_add_and_search_qa(rag_store):
    rag_store.add_qa_pair("How many users are there?", "SELECT COUNT(*) FROM users")
    rag_store.add_qa_pair("List all orders", "SELECT * FROM orders")

    results = rag_store.search_qa("count of users", n=2)
    assert len(results) >= 1
    assert any("users" in r["document"].lower() for r in results)


def test_add_and_search_ddl(rag_store):
    ddl = "CREATE TABLE products (id INT, name TEXT, price DECIMAL);"
    rag_store.add_ddl(ddl, table_name="products")

    results = rag_store.search_ddl("product prices", n=1)
    assert len(results) == 1
    assert "products" in results[0]["document"]


def test_add_and_search_docs(rag_store):
    rag_store.add_documentation("The users table contains customer accounts. Email is unique.")

    results = rag_store.search_docs("customer email", n=1)
    assert len(results) == 1
    assert "email" in results[0]["document"].lower()


def test_search_empty_collection(rag_store):
    results = rag_store.search_qa("anything", n=5)
    assert results == []


def test_upsert_deduplicates(rag_store):
    rag_store.add_qa_pair("How many users?", "SELECT COUNT(*) FROM users")
    rag_store.add_qa_pair("How many users?", "SELECT COUNT(*) FROM users")

    results = rag_store.search_qa("How many users?", n=10)
    assert len(results) == 1


def test_search_returns_distance(rag_store):
    rag_store.add_qa_pair("Total revenue", "SELECT SUM(amount) FROM orders")
    results = rag_store.search_qa("revenue", n=1)
    assert "distance" in results[0]
    assert isinstance(results[0]["distance"], float)


def test_add_and_search_findings(rag_store):
    rag_store.add_finding("Unusual spike in fraud flags for Kotak bank on weekends")
    results = rag_store.search_findings("fraud patterns", n=1)
    assert len(results) == 1
    assert "Kotak" in results[0]["document"]
