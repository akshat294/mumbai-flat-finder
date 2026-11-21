CREATE TABLE IF NOT EXISTS direct_listings (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  locality TEXT NOT NULL,
  zone TEXT NOT NULL DEFAULT 'Mumbai',
  mode TEXT NOT NULL DEFAULT 'rent',
  bhk INTEGER,
  price_inr INTEGER NOT NULL,
  carpet_sqft INTEGER,
  furnishing TEXT,
  zero_brokerage INTEGER NOT NULL DEFAULT 1,
  contact TEXT,
  url TEXT,
  lat REAL,
  lng REAL,
  source TEXT NOT NULL DEFAULT 'owner',
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_direct_expires ON direct_listings(expires_at);
