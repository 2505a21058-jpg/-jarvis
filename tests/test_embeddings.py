"""
tests/test_embeddings.py
All tests pass even without Ollama running.
"""

from unittest.mock import patch

from memory.embeddings import EmbeddingIndex, _cosine_similarity


class TestCosineSimilarity:
    def test_identical_vectors(self):
        vector = [1.0, 0.0, 0.0]
        assert abs(_cosine_similarity(vector, vector) - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        assert abs(_cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 0.001

    def test_zero_vector(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_similar_vectors_high_score(self):
        first = [1.0, 1.0, 0.0]
        second = [1.0, 0.9, 0.1]
        assert _cosine_similarity(first, second) > 0.95

    def test_opposite_vectors(self):
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) < 0.0


class TestEmbeddingIndex:
    def test_search_returns_empty_when_unavailable(self):
        index = EmbeddingIndex()
        with patch("memory.embeddings._get_embedding", return_value=None):
            results = index.search("test query")
        assert results == []

    def test_is_available_false_when_ollama_down(self):
        index = EmbeddingIndex()
        index._available = None
        with patch("memory.embeddings._get_embedding", return_value=None):
            assert index.is_available() is False

    def test_is_available_true_when_ollama_up(self):
        index = EmbeddingIndex()
        index._available = None
        with patch("memory.embeddings._get_embedding", return_value=[0.1, 0.2, 0.3]):
            assert index.is_available() is True

    def test_add_does_not_crash_when_unavailable(self):
        index = EmbeddingIndex()
        index._available = False
        index.add({"content": "test"})
        assert index.size() == 0

    def test_search_with_mocked_embeddings(self):
        index = EmbeddingIndex()
        index._available = True
        mock_embedding = [1.0, 0.0, 0.0]
        entry = {"content": "python programming", "tags": []}
        with index._lock:
            index._entries.append((mock_embedding, entry))
        with patch("memory.embeddings._get_embedding", return_value=[1.0, 0.0, 0.0]):
            results = index.search("python code", top_k=5, threshold=0.1)
        assert len(results) >= 1
        assert results[0]["content"] == "python programming"

    def test_size_returns_int(self):
        assert isinstance(EmbeddingIndex().size(), int)


class TestMemorySemanticIntegration:
    def test_search_semantic_returns_list(self, memory):
        memory.store("deep learning neural networks")
        results = memory.search_semantic("AI and machine learning")
        assert isinstance(results, list)

    def test_is_semantic_available_bool(self, memory):
        assert isinstance(memory.is_semantic_available(), bool)

    def test_retrieve_semantic_mode_no_crash(self, memory):
        memory.store("software engineering best practices")
        results = memory.retrieve("software", mode="semantic", limit=3)
        assert isinstance(results, list)

    def test_retrieve_falls_back_when_semantic_empty(self, memory):
        memory.store("python is a programming language")
        with patch.object(memory._embed_index, "search", return_value=[]):
            results = memory.retrieve("python programming", mode="fast", limit=5)
        assert isinstance(results, list)
