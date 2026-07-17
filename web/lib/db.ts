import { neon } from "@neondatabase/serverless";

// neon() is safe to initialise with an empty string; it only throws at query
// time, so Next.js build can import this module without DATABASE_URL set.
const sql = neon(process.env.DATABASE_URL ?? "");
export default sql;
