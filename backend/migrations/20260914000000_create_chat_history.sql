-- Chat history table for document-grounded conversations
-- Table: chat_history

CREATE TABLE IF NOT EXISTS chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE NOT NULL,
    user_id UUID NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    citations JSONB DEFAULT '[]'::jsonb,
    confidence_score INTEGER,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Enable Row Level Security
ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;

-- Policy: Authenticated users can only view their own chat history
CREATE POLICY "Users can view own chat history"
    ON chat_history
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- Policy: Authenticated users can only insert their own chat history
CREATE POLICY "Users can insert own chat history"
    ON chat_history
    FOR INSERT
    TO authenticated
    WITH CHECK (auth.uid() = user_id);

-- Policy: Authenticated users can only delete their own chat history
CREATE POLICY "Users can delete own chat history"
    ON chat_history
    FOR DELETE
    TO authenticated
    USING (auth.uid() = user_id);

-- Index for efficient queries
CREATE INDEX IF NOT EXISTS idx_chat_history_document_user
    ON chat_history (document_id, user_id);

CREATE INDEX IF NOT EXISTS idx_chat_history_timestamp
    ON chat_history (timestamp);
