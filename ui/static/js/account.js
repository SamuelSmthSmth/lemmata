// Accounts: signing in, and syncing this browser's work with the account.
//
// Only when site.json names a Supabase project (`accounts: {url, key}`);
// otherwise nothing here loads and work stays in the browser, as before.
// supabase-js is vendored (ui/vendor_supabase.py) and imported on demand.
//
// Sign-in is passwordless: an emailed link, or a provider the project has
// turned on (read from the project, so a provider appears here when it is
// enabled there).  Both return to this page with a one-time code, which
// supabase-js exchanges for a session (PKCE).  Signed in, js/sync-local.js
// syncs everything with the account; signed out, the work stays here.
//
// Not in the desktop app yet: its pages are not at a web address a provider
// can return to.

import { connectSync, forgetSyncState } from "./sync-local.js";
import { createSupabaseRemote } from "./remote-supabase.js";
import { desktop, site } from "./site.js";

/** Providers the app knows how to present, in the order it presents them. */
export const PROVIDERS = [
  { id: "google", label: "Google" },
  { id: "azure", label: "Microsoft", scopes: "email" },
  { id: "github", label: "GitHub" },
  { id: "discord", label: "Discord" },
];

export const account = {
  /** Accounts are configured for this site and this shell. */
  available: false,
  /** Provider ids the project has turned on (email aside). */
  providers: [],
  email: false,
  user: null,
  /** {state: "off" | "syncing" | "synced" | "error", at?, error?, pending?} */
  status: { state: "off" },
};

const listeners = new Set();
let client = null;
let remote = null;
let sync = null;

export function onAccount(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit() {
  for (const fn of listeners) fn(account);
}

/** Where a sign-in link or provider returns: this page, without its query. */
function returnUrl() {
  return `${location.origin}${location.pathname}`;
}

async function enabledProviders() {
  try {
    const response = await fetch(`${site.accounts.url}/auth/v1/settings`, { headers: { apikey: site.accounts.key } });
    const settings = await response.json();
    const external = settings.external ?? {};
    return { email: Boolean(external.email), providers: PROVIDERS.filter((p) => external[p.id]).map((p) => p.id) };
  } catch (error) {
    // Offline: offer what is most likely on; a sign-in needs the network anyway.
    return { email: true, providers: [] };
  }
}

export async function initAccount() {
  if (!site.accounts || desktop) return account;
  const { createClient } = await import("../vendor/supabase/supabase.mjs");
  client = createClient(site.accounts.url, site.accounts.key, {
    auth: { flowType: "pkce", storageKey: "aether:auth", persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  account.available = true;
  Object.assign(account, await enabledProviders());
  // Supabase asks that the callback not await its own calls: defer to a task.
  client.auth.onAuthStateChange((_event, session) => setTimeout(() => adopt(session), 0));
  const { data } = await client.auth.getSession();
  adopt(data.session);
  window.addEventListener("online", () => sync?.syncNow());
  emit();
  return account;
}

/** A provider's error, carried back on the return URL. */
export function returnedError() {
  const params = new URLSearchParams(location.search);
  const hash = new URLSearchParams(location.hash.replace(/^#/, ""));
  return params.get("error_description") || hash.get("error_description") || null;
}

function adopt(session) {
  const user = session?.user ?? null;
  if ((user?.id ?? null) === (account.user?.id ?? null)) {
    account.user = user;
    return;
  }
  sync?.disconnect();
  sync = null;
  remote = null;
  account.user = user;
  account.status = { state: "off" };
  if (user) {
    remote = createSupabaseRemote(client, user.id);
    sync = connectSync({
      remote,
      owner: user.id,
      onStatus: (status) => {
        account.status = status;
        emit();
      },
    });
  }
  emit();
}

export async function signInWithEmail(email) {
  const { error } = await client.auth.signInWithOtp({ email, options: { emailRedirectTo: returnUrl() } });
  if (error) throw error;
}

export async function signInWith(providerId) {
  const provider = PROVIDERS.find((p) => p.id === providerId);
  const { error } = await client.auth.signInWithOAuth({
    provider: providerId,
    options: { redirectTo: returnUrl(), ...(provider?.scopes ? { scopes: provider.scopes } : {}) },
  });
  if (error) throw error;
}

/** Sign out here.  The work stays in this browser; the account keeps its copy. */
export async function signOut() {
  sync?.disconnect();
  sync = null;
  await client.auth.signOut({ scope: "local" });
  forgetSyncState();
  adopt(null);
}

export const syncNow = () => sync?.syncNow();

/** Everything the account holds, as one JSON document. */
export async function exportAccount() {
  const records = await remote.everything();
  return {
    format: "lemmata-account-export",
    exported: new Date().toISOString(),
    email: account.user?.email ?? null,
    records,
  };
}

/** Delete the account and everything synced to it.  This browser's copy stays. */
export async function deleteAccount() {
  const { error } = await client.rpc("delete_my_account");
  if (error) throw error;
  await signOut();
}
