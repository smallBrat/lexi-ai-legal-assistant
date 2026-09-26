-- Comparisons table for clause-by-clause document comparison
-- Table: comparisons
--
-- Stores the structured Gemini comparison JSON for a pair of analyzed
-- documents owned by the same user. Pairs are cached order-independently:
-- (A, B) and (B, A) always resolve to the same canonical row
-- (document_a_id < document_b_id lexicographically).

CREATE TABLE IF NOT EXISTS comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_a_id UUID REFERENCES documents(id) ON DELETE CASCADE NOT NULL,
    document_b_id UUID REFERENCES documents(id) ON DELETE CASCADE NOT NULL,
    user_id UUID NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT comparisons_pair_order CHECK (document_a_id::text < document_b_id::text),
    CONSTRAINT comparisons_distinct_pair CHECK (document_a_id <> document_b_id)
);

-- Enable Row Level Security
ALTER TABLE comparisons ENABLE ROW LEVEL SECURITY;

-- Policy: Authenticated users can only view their own comparisons
CREATE POLICY "Users can view own comparisons"
    ON comparisons
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- Policy: Authenticated users can only insert their own comparisons
CREATE POLICY "Users can insert own comparisons"
    ON comparisons
    FOR INSERT
    TO authenticated
    WITH CHECK (auth.uid() = user_id);

-- Policy: Authenticated users can only delete their own comparisons
CREATE POLICY "Users can delete own comparisons"
    ON comparisons
    FOR DELETE
    TO authenticated
    USING (auth.uid() = user_id);

-- Index for pair lookups (cache hits) and history listing
CREATE INDEX IF NOT EXISTS idx_comparisons_pair_user
    ON comparisons (document_a_id, document_b_id, user_id);

CREATE INDEX IF NOT EXISTS idx_comparisons_user_created
    ON comparisons (user_id, created_at DESC);
