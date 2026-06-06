from dotenv import load_dotenv

# Load environment variables from .env (embedding_model, embedding_device)
load_dotenv("../.env")

from app.core.embeddings import EmbeddingModel

# Qwen3-Embedding-0.6B always outputs 1024-dim vectors.
# This is a hard contract with the pgvector column (vector(1024)).
EXPECTED_DIM = 1024


def test():
    # First run downloads ~600 MB from HuggingFace and caches locally.
    # Subsequent runs load from cache and are fast.
    print("Loading Qwen3-Embedding-0.6B (first run downloads ~600 MB, be patient)...")
    model = EmbeddingModel()

    # --- dimensions property ---
    # Verifies EmbeddingModel.dimensions reads the correct value from the model.
    # Used at startup to guard the pgvector schema creation.
    dims = model.dimensions
    print(f"Model reports {dims} dimensions")
    assert dims == EXPECTED_DIM, f"Expected {EXPECTED_DIM} dims, got {dims}"

    # --- single embed ---
    # Verifies embed() returns a flat list of floats with the correct length.
    text = "Total revenue for Q3 was $4.2 million, up 18% year-over-year."
    vec = model.embed(text)
    print(f"embed()       → {len(vec)} dims, first 4 values: {[round(v, 4) for v in vec[:4]]}")
    assert len(vec) == EXPECTED_DIM, f"embed() returned {len(vec)} dims"
    assert all(isinstance(v, float) for v in vec), "embed() values are not floats"

    # --- normalised (L2 norm ≈ 1.0) ---
    # normalize_embeddings=True is set in EmbeddingModel.embed().
    # Cosine similarity in pgvector is only correct on unit-normalised vectors.
    # Tolerance is 1e-3 (not 1e-4) because float32 rounding over 1024 dims causes tiny drift.
    norm = sum(v * v for v in vec) ** 0.5
    print(f"L2 norm       → {norm:.6f} (should be ~1.0)")
    assert abs(norm - 1.0) < 1e-3, f"Vector not normalised: norm={norm}"

    # --- batch embed (2 strings — original test kept) ---
    # Original smoke test for embed_batch() with a small input.
    texts_2 = [
        "Patient readmission rate dropped by 12% after discharge protocol update.",
        "Monthly active users grew 23% following the onboarding redesign.",
    ]
    vecs_2 = model.embed_batch(texts_2)
    print(f"embed_batch() [2 strings]  → {len(vecs_2)} vectors, each {len(vecs_2[0])} dims")
    assert len(vecs_2) == 2, "embed_batch() wrong number of vectors"
    assert all(len(v) == EXPECTED_DIM for v in vecs_2), "embed_batch() wrong dims"

    # --- batch embed (10 strings — extended test) ---
    # Tests embed_batch() at a realistic batch size covering all domain types
    # the platform handles: Finance, Healthcare, Retail, Marketing, Operations.
    # Also verifies normalisation and distinctness for every vector in the batch.
    texts_10 = [
        "Total revenue for Q3 was $4.2 million, up 18% year-over-year.",             # Finance
        "Patient readmission rate dropped by 12% after discharge protocol update.",  # Healthcare
        "Monthly active users grew 23% following the onboarding redesign.",          # Product
        "Average order value increased from $42 to $56 after upsell campaign.",      # Retail
        "Cost per acquisition fell to $18 after optimising the paid search channel.", # Marketing
        "Inventory turnover ratio improved from 4.2 to 5.8 over the quarter.",       # Operations
        "Net promoter score rose to 67 following the support experience revamp.",    # Operations
        "Gross margin held steady at 61% despite rising supplier costs.",            # Finance
        "Customer lifetime value is estimated at $340 for the premium cohort.",      # Marketing
        "Churn rate decreased from 3.1% to 1.9% after the retention email flow.",   # Finance
    ]
    vecs_10 = model.embed_batch(texts_10)
    print(f"embed_batch() [10 strings] → {len(vecs_10)} vectors, each {len(vecs_10[0])} dims")

    # Correct count returned
    assert len(vecs_10) == 10, f"Expected 10 vectors, got {len(vecs_10)}"

    # Every vector has the correct dimension
    assert all(len(v) == EXPECTED_DIM for v in vecs_10), "embed_batch() wrong dims"

    # Every value is a float
    assert all(isinstance(v, float) for vec in vecs_10 for v in vec), "Non-float values in batch"

    # Every vector is unit-normalised (required for pgvector cosine similarity)
    for i, vec in enumerate(vecs_10):
        norm = sum(v * v for v in vec) ** 0.5
        assert abs(norm - 1.0) < 5e-3, f"Vector {i} not normalised: norm={norm}"

    # Every vector is distinct — proves the model encodes meaning, not a constant output
    for i in range(len(vecs_10)):
        for j in range(i + 1, len(vecs_10)):
            assert vecs_10[i] != vecs_10[j], f"Vectors {i} and {j} are identical"

    print()
    print("All assertions passed.")


test()
