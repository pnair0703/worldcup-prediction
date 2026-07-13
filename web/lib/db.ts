import { neon } from "@neondatabase/serverless";

const url = process.env.DATABASE_URL;
if (!url || url.includes("placeholder")) {
  throw new Error("DATABASE_URL is not configured — set it in Vercel environment variables");
}

const sql = neon(url);
export default sql;
