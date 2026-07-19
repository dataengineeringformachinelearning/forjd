import { Injectable, OnDestroy } from '@angular/core';
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
export class SupabaseService implements OnDestroy {
  private readonly client: SupabaseClient | null;
  private channel: RealtimeChannel | null = null;
  private authSubscription: { unsubscribe(): void } | null = null;

  readonly session$ = new BehaviorSubject<Session | null>(null);
  readonly configured = Boolean(environment.supabaseUrl && environment.supabaseAnonKey);

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
    const { data } = this.client.auth.onAuthStateChange((_event, session) =>
      this.session$.next(session),
    );
    this.authSubscription = data.subscription;
  }

  ngOnDestroy(): void {
    this.authSubscription?.unsubscribe();
    void this.unsubscribeTelemetry();
    this.session$.complete();
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
    const { error } = await this.client.auth.signOut();
    if (error) throw error;
  }

  async accessToken(): Promise<string | null> {
    if (!this.client) return null;
    const { data, error } = await this.client.auth.getSession();
    if (error) throw error;
    return data.session?.access_token ?? null;
  }

  /** Subscribe only to metadata for sealed events visible through tenant RLS. */
  subscribeTelemetry(tenantId: string, onInsert: (row: TelemetryRealtimeRow) => void): () => void {
    if (!this.client) return () => undefined;
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
    return () => void this.unsubscribeTelemetry();
  }

  private async unsubscribeTelemetry(): Promise<void> {
    const channel = this.channel;
    this.channel = null;
    if (this.client && channel) await this.client.removeChannel(channel);
  }
}
