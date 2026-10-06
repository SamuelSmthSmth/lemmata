// The sync remote over Supabase (supabase/migrations/): the remote interface
// js/sync.js expects, for one signed-in student.
//
//   push     the sync_push function, which keeps the newest edit of each
//            record atomically and names the ones it refused
//   pull     the sync_records rows after a cursor, in seq order (RLS returns
//            only this student's)
//   subscribe  Realtime: a row changed, so it is time to pull

const COLUMNS = "store,key,data,modified,deleted,seq";

export function createSupabaseRemote(client, userId) {
  return {
    async push(records) {
      const { data, error } = await client.rpc("sync_push", { records });
      if (error) throw error;
      return data ?? { rejected: [] };
    },
    async pull(cursor = 0, limit = 500) {
      const { data, error } = await client.from("sync_records").select(COLUMNS).gt("seq", cursor).order("seq").limit(limit);
      if (error) throw error;
      const records = data ?? [];
      return { records, cursor: records.length ? records[records.length - 1].seq : cursor };
    },
    subscribe(fn) {
      const channel = client
        .channel(`sync:${userId}`)
        .on("postgres_changes", { event: "*", schema: "public", table: "sync_records", filter: `user_id=eq.${userId}` }, (payload) => fn(payload.new))
        .subscribe();
      return () => client.removeChannel(channel);
    },
    /** Every record, for "Download my data". */
    async everything() {
      const out = [];
      for (let cursor = 0; ; ) {
        const { records, cursor: next } = await this.pull(cursor, 1000);
        out.push(...records);
        if (records.length < 1000) return out;
        cursor = next;
      }
    },
  };
}
