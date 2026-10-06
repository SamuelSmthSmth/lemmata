// The database the app syncs to (supabase/migrations/), checked on PGlite:
// Postgres compiled to WASM, so no Docker or Supabase CLI is needed.
//
// Supabase's own `auth` schema is stood in for by the little that the
// migrations use (auth.users, auth.uid() from the request's JWT claim), and
// the roles the API runs as (anon, authenticated).  Then every migration runs,
// twice (they must be safe to re-run), and the rules sync relies on are
// checked: newest edit wins and the older is named, tombstones, seq order,
// row-level security, no direct writes, sign-in required, the 5 MB limit,
// and deleting an account.
//
//   npm --prefix supabase ci && node supabase/verify_supabase.mjs

import { PGlite } from "@electric-sql/pglite";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const MIGRATIONS = join(dirname(fileURLToPath(import.meta.url)), "migrations");
const migrations = readdirSync(MIGRATIONS).filter((f) => f.endsWith(".sql")).sort().map((f) => readFileSync(join(MIGRATIONS, f), "utf8"));
const db = new PGlite();
const ok = (c, m) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) process.exitCode = 1; };
await db.exec(`
  create role anon; create role authenticated;
  create schema auth;
  create table auth.users (id uuid primary key);
  create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
  grant usage on schema auth, public to anon, authenticated;
  grant execute on function auth.uid() to anon, authenticated;
  insert into auth.users values ('00000000-0000-0000-0000-00000000000a'), ('00000000-0000-0000-0000-00000000000b');
`);
for (const sql of migrations) await db.exec(sql);
for (const sql of migrations) await db.exec(sql); // safe to re-run
const A = "00000000-0000-0000-0000-00000000000a", B = "00000000-0000-0000-0000-00000000000b";
async function as(uid, sql, params = []) {
  await db.exec(`reset role; select set_config('request.jwt.claim.sub', '${uid ?? ""}', false); set role ${uid ? "authenticated" : "anon"};`);
  try { return await db.query(sql, params); } finally { await db.exec("reset role"); }
}
const push = (uid, recs) => as(uid, "select public.sync_push($1::jsonb) as r", [JSON.stringify(recs)]).then((x) => x.rows[0].r);
const f = (key, modified, data = { source: key + modified }) => ({ store: "files", key, data, modified, deleted: false });

let r = await push(A, [f("f1", 10), f("f2", 10)]);
ok(r.rejected.length === 0, "a first push is kept");
r = await push(A, [f("f1", 5)]);
ok(JSON.stringify(r.rejected) === '["files:f1"]', "an older edit is refused and named");
r = await push(A, [f("f1", 20)]);
ok(r.rejected.length === 0, "a newer edit is kept");
r = await push(A, [{ store: "files", key: "f2", data: { x: 1 }, modified: 30, deleted: true }]);
const rows = (await as(A, "select key, data, deleted, seq from public.sync_records order by seq")).rows;
ok(rows.length === 2 && rows.find((x) => x.key === "f2").deleted && rows.find((x) => x.key === "f2").data === null, "a deletion is a tombstone without data");
ok(rows.map((x) => x.key).join() === "f1,f2", "seq orders the writes");
await push(B, [f("f1", 1)]);
ok((await as(B, "select * from public.sync_records")).rows.length === 1, "a student sees only their own records");
ok((await as(A, "select * from public.sync_records")).rows.length === 2, "and the other student theirs");
let err = null;
try { await as(A, "insert into public.sync_records (user_id, store, key, modified, seq) values ($1, 'files', 'x', 1, 1)", [A]); } catch (e) { err = e; }
ok(err !== null, "writing to the table directly is refused");
err = null;
try { await push(null, [f("z", 1)]); } catch (e) { err = e; }
ok(err !== null, "a visitor who is not signed in cannot push");
err = null;
try { await push(A, [{ store: "secrets", key: "k", data: 1, modified: 1 }]); } catch (e) { err = e; }
ok(err !== null, "an unknown store is refused");
err = null;
try { await push(A, [f("big", 1, { s: "x".repeat(5 * 1024 * 1024 + 10) })]); } catch (e) { err = e; }
ok(err && /5 MB/.test(err.message), "a record over 5 MB is refused");
await as(A, "select public.delete_my_account()");
ok((await db.query("select count(*)::int as n from public.sync_records where user_id = $1", [A])).rows[0].n === 0, "deleting the account deletes its records");
ok((await db.query("select count(*)::int as n from public.sync_records where user_id = $1", [B])).rows[0].n === 1, "and nobody else's");
console.log(process.exitCode ? "\nsupabase checks FAILED" : "\nsupabase checks passed");
