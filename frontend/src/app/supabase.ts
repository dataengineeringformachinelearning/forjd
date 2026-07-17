import { Injectable } from '@angular/core';
import { createClient, RealtimeChannel, SupabaseClient, type Session } from '@supabase/supabase-js';
import { BehaviorSubject } from 'rxjs';

import { environment } from '../environments/environment';

export type TelemetryRealtimeRow = {
  id: string;
  tenant_id: string;
  client_event_id: string;
  created_at: string;
  key_id: string;
  ciphertext_sha256: string | null;
};

@Injectable({ providedIn: 'root' })
export class SupabaseService {
  private readonly client: SupabaseClient | null;
  private channel: RealtimeChannel | null = null;

  readonly session$ = new BehaviorSubject<Session | null>(null);
  readonly configured = Boolean(
    environment.supabaseUrl && environment.supabaseAnonKey,
  );

  constructor() {
    if (!this.configured) {
      this.client = null;
      return;
    }
    this.client = createClient(environment.supabaseUrl, environment.supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
    void this.client.auth.getSession().then(({ data }) => this.session$.next(data.session));
    this.client.auth.onAuthStateChange((_event, session) => this.session$.next(session));
  }

  get raw(): SupabaseClient | null {
    return this.client;
  }

  async signIn(email: string, password: string): Promise<void> {
    if (!this.client) throw new Error('Supabase anon key not configured');
    const { error } = await this.client.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }

  async signUp(email: string, password: string): Promise<void> {
    if (!this.client) throw new Error('Supabase anon key not configured');
    const { error } = await this.client.auth.signUp({ email, password });
    if (error) throw error;
  }

  async signOut(): Promise<void> {
    if (!this.client) return;
    await this.client.auth.signOut();
  }

  async accessToken(): Promise<string | null> {
    if (!this.client) return null;
    const { data } = await this.client.auth.getSession();
    return data.session?.access_token ?? null;
  }

  /**
   * Subscribe to sealed telemetry inserts for one tenant (RLS filters rows).
   * Enable Realtime on `telemetry_events` in the Supabase dashboard if needed.
   */
  subscribeTelemetry(
    tenantId: string,
    onInsert: (row: TelemetryRealtimeRow) => void,
  ): () => void {
    if (!this.client) {
      return () => undefined;
    }
    void this.unsubscribeTelemetry();
    this.channel = this.client
      .channel(`telemetry:${tenantId}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'telemetry_events',
          filter: `tenant_id=eq.${tenantId}`,
        },
        (payload) => onInsert(payload.new as TelemetryRealtimeRow),
      )
      .subscribe();
    return () => {
      void this.unsubscribeTelemetry();
    };
  }

  private async unsubscribeTelemetry(): Promise<void> {
    if (this.client && this.channel) {
      await this.client.removeChannel(this.channel);
      this.channel = null;
    }
  }
}
