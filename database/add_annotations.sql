-- Add annotation columns to companies table
ALTER TABLE companies ADD COLUMN IF NOT EXISTS is_reviewed BOOLEAN DEFAULT FALSE;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS classification VARCHAR(100) DEFAULT NULL;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT NULL;

-- Add indexes for the new columns
CREATE INDEX IF NOT EXISTS idx_companies_is_reviewed ON companies(is_reviewed);
CREATE INDEX IF NOT EXISTS idx_companies_classification ON companies(classification);

-- Update existing records to have default values
UPDATE companies SET is_reviewed = FALSE WHERE is_reviewed IS NULL; 