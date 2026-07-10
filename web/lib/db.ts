import { neon } from "@neondatabase/serverless";

// DATABASE_URL must be set at runtime; validated here so API routes get a
// clear error rather than a cryptic Neon connection failure.
const sql = neon(process.env.DATABASE_URL ?? "postgresql://placeholder/placeholder");
export default sql;
