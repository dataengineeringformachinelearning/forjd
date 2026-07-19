import { DecimalPipe, JsonPipe } from '@angular/common';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { FjButton, FjPanel, FjStatusItem, FjStatusList } from 'forjd-ui';

import { generateAesKey, seal } from './crypto/seal';
import { generateX25519KeyPair } from './crypto/x25519';
import { AnomalyScoreResult, PulseApi, PulseResult, StackStatus } from './pulse-api';
import { IngestResult, SecureApi, Tenant } from './secure-api';
import { SupabaseService, TelemetryRealtimeRow } from './supabase';
import { environment } from '../environments/environment';
import { firstValueFrom } from 'rxjs';

@Component({
  selector: 'app-root',
  imports: [FjButton, FjPanel, FjStatusList, JsonPipe, DecimalPipe, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit, OnDestroy {
  private readonly api = inject(PulseApi);
  private readonly secure = inject(SecureApi);
  private readonly supabase = inject(SupabaseService);
  private unsubRealtime: (() => void) | null = null;

  protected readonly title = signal('FORJD');
  protected readonly docsUrl = `${environment.apiBaseUrl}/docs`;
  protected readonly stack = signal<StackStatus | null>(null);
  protected readonly pulse = signal<PulseResult | null>(null);
  protected readonly anomaly = signal<AnomalyScoreResult | null>(null);
  protected readonly busy = signal(false);
  protected readonly anomalyBusy = signal(false);
  protected readonly secureBusy = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly supabaseReady = this.supabase.configured;
  protected readonly sessionEmail = signal<string | null>(null);
  protected readonly tenants = signal<Tenant[]>([]);
  protected readonly activeTenantId = signal<string | null>(null);
  protected readonly ingestResult = signal<IngestResult | null>(null);
  protected readonly realtimeEvents = signal<TelemetryRealtimeRow[]>([]);

  protected email = '';
  protected password = '';
  protected tenantSlug = 'demo';
  protected tenantName = 'Demo tenant';

  protected readonly stackChecks = computed<FjStatusItem[] | null>(() => {
    const s = this.stack();
    if (!s) return null;
    return Object.entries(s.checks).map(([name, value]) => ({
      name,
      ok: value.ok,
      stateLabel: value.ok ? 'ok' : 'down',
    }));
  });

  ngOnInit(): void {
    this.refreshStack();
    this.supabase.session$.subscribe((session) => {
      this.sessionEmail.set(session?.user?.email ?? null);
      if (session) {
        this.refreshTenants();
      } else {
        this.tenants.set([]);
        this.activeTenantId.set(null);
        this.unsubRealtime?.();
        this.unsubRealtime = null;
      }
    });
  }

  ngOnDestroy(): void {
    this.unsubRealtime?.();
  }

  protected refreshStack(): void {
    this.api.stack().subscribe({
      next: (s) => {
        this.stack.set(s);
        this.error.set(null);
      },
      error: (err: unknown) => {
        this.stack.set(null);
        this.error.set(this.errMsg(err, 'API unreachable — is the backend running?'));
      },
    });
  }

  protected runPulse(): void {
    this.busy.set(true);
    this.error.set(null);
    this.api.pulse().subscribe({
      next: (p) => {
        this.pulse.set(p);
        this.busy.set(false);
        this.refreshStack();
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(this.errMsg(err, 'Pulse failed'));
      },
    });
  }

  protected runAnomaly(): void {
    this.anomalyBusy.set(true);
    this.error.set(null);
    this.api.fitAnomaly().subscribe({
      next: (fit) => {
        if (!fit.ok) {
          this.anomalyBusy.set(false);
          this.error.set(
            fit.error ?? 'Anomaly fit failed — is torch installed? (uv sync --group ml)',
          );
          return;
        }
        this.api.scoreAnomaly().subscribe({
          next: (score) => {
            this.anomaly.set(score);
            this.anomalyBusy.set(false);
            this.refreshStack();
            if (!score.ok) {
              this.error.set(score.error ?? 'Anomaly score failed');
            }
          },
          error: (err: unknown) => {
            this.anomalyBusy.set(false);
            this.error.set(this.errMsg(err, 'Anomaly score failed'));
          },
        });
      },
      error: (err: unknown) => {
        this.anomalyBusy.set(false);
        this.error.set(this.errMsg(err, 'Anomaly fit failed'));
      },
    });
  }

  protected async signIn(): Promise<void> {
    this.error.set(null);
    try {
      await this.supabase.signIn(this.email.trim(), this.password);
    } catch (err: unknown) {
      this.error.set(this.errMsg(err, 'Sign-in failed'));
    }
  }

  protected async signUp(): Promise<void> {
    this.error.set(null);
    try {
      await this.supabase.signUp(this.email.trim(), this.password);
    } catch (err: unknown) {
      this.error.set(this.errMsg(err, 'Sign-up failed'));
    }
  }

  protected async signOut(): Promise<void> {
    await this.supabase.signOut();
  }

  protected refreshTenants(): void {
    this.secure.listTenants().subscribe({
      next: (res) => {
        this.tenants.set(res.tenants);
        if (!this.activeTenantId() && res.tenants[0]) {
          this.selectTenant(res.tenants[0].id);
        }
      },
      error: (err: unknown) => {
        this.error.set(this.errMsg(err, 'Could not list tenants'));
      },
    });
  }

  protected createTenant(): void {
    this.secureBusy.set(true);
    this.error.set(null);
    this.secure.createTenant(this.tenantSlug.trim(), this.tenantName.trim()).subscribe({
      next: (res) => {
        this.secureBusy.set(false);
        this.selectTenant(res.tenant.id);
        this.refreshTenants();
      },
      error: (err: unknown) => {
        this.secureBusy.set(false);
        this.error.set(this.errMsg(err, 'Create tenant failed'));
      },
    });
  }

  protected selectTenant(id: string): void {
    this.activeTenantId.set(id);
    this.realtimeEvents.set([]);
    this.unsubRealtime?.();
    this.unsubRealtime = this.supabase.subscribeTelemetry(id, (row) => {
      this.realtimeEvents.update((prev) => [row, ...prev].slice(0, 10));
    });
  }

  protected async sealAndIngest(): Promise<void> {
    const tenantId = this.activeTenantId();
    if (!tenantId) {
      this.error.set('Create or select a tenant first');
      return;
    }
    this.secureBusy.set(true);
    this.error.set(null);
    try {
      // Register public key so envelope.key_id binds to crypto_sessions (prod).
      const identity = await generateX25519KeyPair();
      const sessionId = 'poc-device-key-1';
      await firstValueFrom(
        this.secure.upsertSession({
          tenantId,
          sessionId,
          identityPublicKey: identity.publicKeyB64,
        }),
      );

      const key = await generateAesKey();
      const clientEventId = crypto.randomUUID();
      // Opaque ratchet placeholder — full Double Ratchet lands in a later SDK.
      const ratchetHeader = btoa(`poc-ratchet:${clientEventId}`);
      const envelope = await seal(
        JSON.stringify({
          kind: 'event.poc',
          values: [1, 2, 3, 5, 8],
          ts: Date.now(),
        }),
        {
          key,
          keyId: sessionId,
          tenantId,
          clientEventId,
          ratchetHeader,
        },
      );
      const res = await firstValueFrom(
        this.secure.ingestSealed({
          tenantId,
          clientEventId,
          envelope,
          metadata: { source: 'angular' },
        }),
      );
      this.ingestResult.set(res);
      this.secureBusy.set(false);
    } catch (err: unknown) {
      this.secureBusy.set(false);
      this.error.set(this.errMsg(err, 'Secure ingest failed'));
    }
  }

  protected layerEntries(): FjStatusItem[] {
    const layers = this.pulse()?.layers;
    if (!layers) return [];
    return Object.entries(layers).map(([name, value]) => ({
      name,
      ok: Boolean(value?.ok),
      stateLabel: value?.ok ? 'ok' : 'fail',
    }));
  }

  private errMsg(err: unknown, fallback: string): string {
    if (err && typeof err === 'object') {
      if ('error' in err && err.error && typeof err.error === 'object' && 'message' in err.error) {
        return String((err.error as { message: unknown }).message);
      }
      if ('message' in err) {
        return String((err as { message: unknown }).message);
      }
    }
    return fallback;
  }
}
