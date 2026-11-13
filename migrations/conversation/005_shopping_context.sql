-- Browser shopping dialogue shares the existing session lock and turn transaction.
ALTER TABLE sessions ADD COLUMN shopping_context jsonb NOT NULL DEFAULT '{}'
    CHECK (jsonb_typeof(shopping_context) = 'object');
