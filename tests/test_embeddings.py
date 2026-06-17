import builtins
import unittest
from unittest.mock import patch

from app.rag.embeddings import HuggingFaceLocalEmbeddings


class EmbeddingDependencyTests(unittest.TestCase):
    def test_huggingface_embeddings_fall_back_when_sentence_transformers_missing(self) -> None:
        real_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "sentence_transformers":
                raise ImportError("sentence-transformers is optional in runtime images")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            embeddings = HuggingFaceLocalEmbeddings()

        self.assertIsNone(embeddings.model)
        self.assertEqual(len(embeddings.embed_query("diabetes follow up")), 384)


if __name__ == "__main__":
    unittest.main()