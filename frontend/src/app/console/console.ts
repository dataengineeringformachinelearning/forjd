import { DecimalPipe, JsonPipe } from '@angular/common';
import { Component, DestroyRef, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { FjButton, FjPanel, FjStatusItem, FjStatusList } from 'forjd-ui';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../environments/environment';
import { importAesKeyRaw, seal } from '../crypto/seal';
import { deriveSessionKeyRaw, generateX25519KeyPair } from '../crypto/x25519';
import { AnomalyScoreResult, PulseApi, PulseResult, StackStatus } from '../pulse-api';
import { IngestResult, SecureApi, Tenant } from '../secure-api';
import { SupabaseService, TelemetryRealtimeRow } from '../supabase';

// --- Authenticated operational console ---
@Component({
  selector: 'app-console',
  imports: [RouterLink, FjButton, FjPanel, FjStatusList, JsonPipe, DecimalPipe, FormsModule],
  templateUrl: './console.html',
  styleUrl: './console.scss',
})
export class Console implements OnInit, OnDestroy {
  private readonly destroyRef = inject(DestroyRef);
  private readonly api = inject(PulseApi);
  private readonly secure = inject(SecureApi);
  private readonly supabase = inject(SupabaseService);
  private unsubscribeRealtime: (() => void) | null = null;

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
    const stack = this.stack();
    if (!stack) return null;
    return Object.entries(stack.checks).map(([name, value]) => ({
      name,
      ok: value.ok,
      stateLabel: value.ok ? 'ok' : 'down',
    }));
  });

  ngOnInit(): void {
    this.refreshStack();
    this.supabase.session$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((session) => {
      this.sessionEmail.set(session?.user?.email ?? null);
      if (session) {
        this.refreshTenants();
        return;
      }
      this.tenants.set([]);
      this.activeTenantId.set(null);
      this.realtimeEvents.set([]);
      this.unsubscribeRealtime?.();
      this.unsubscribeRealtime = null;
    });
  }

  ngOnDestroy(): void {
    this.unsubscribeRealtime?.();
  }

  protected refreshStack(): void {
    this.api.stack().subscribe({
      next: (stack) => {
        this.stack.set(stack);
        this.error.set(null);
      },
      error: (error: unknown) => {
        this.stack.set(null);
        this.error.set(this.errMsg(error, 'API unreachable — is the backend running?'));
      },
    });
  }

  protected runPulse(): void {
    this.busy.set(true);
    this.error.set(null);
    this.api.pulse().subscribe({
      next: (pulse) => {
        this.pulse.set(pulse);
        this.busy.set(false);
        this.refreshStack();
      },
      error: (error: unknown) => {
        this.busy.set(false);
        this.error.set(this.errMsg(error, 'Pulse failed'));
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
          this.error.set(fit.error ?? 'Anomaly fit failed');
          return;
        }
        this.api.scoreAnomaly().subscribe({
          next: (score) => {
            this.anomaly.set(score);
            this.anomalyBusy.set(false);
            this.refreshStack();
            if (!score.ok) this.error.set(score.error ?? 'Anomaly score failed');
          },
          error: (error: unknown) => {
            this.anomalyBusy.set(false);
            this.error.set(this.errMsg(error, 'Anomaly score failed'));
          },
        });
      },
      error: (error: unknown) => {
        this.anomalyBusy.set(false);
        this.error.set(this.errMsg(error, 'Anomaly fit failed'));
      },
    });
  }

  protected async signIn(): Promise<void> {
    this.error.set(null);
    try {
      await this.supabase.signIn(this.email.trim(), this.password);
    } catch (error: unknown) {
      this.error.set(this.errMsg(error, 'Sign-in failed'));
    } finally {
      this.password = '';
    }
  }

  protected async signUp(): Promise<void> {
    this.error.set(null);
    try {
      await this.supabase.signUp(this.email.trim(), this.password);
    } catch (error: unknown) {
      this.error.set(this.errMsg(error, 'Sign-up failed'));
    } finally {
      this.password = '';
    }
  }

  protected async signOut(): Promise<void> {
    this.error.set(null);
    try {
      await this.supabase.signOut();
    } catch (error: unknown) {
      this.error.set(this.errMsg(error, 'Sign-out failed'));
    } finally {
      this.password = '';
    }
  }

  protected refreshTenants(): void {
    this.secure.listTenants().subscribe({
      next: ({ tenants }) => {
        this.tenants.set(tenants);
        const selected = this.activeTenantId();
        if (selected && !tenants.some(({ id }) => id === selected)) {
          this.activeTenantId.set(null);
        }
        if (!this.activeTenantId() && tenants[0]) this.selectTenant(tenants[0].id);
      },
      error: (error: unknown) => {
        this.error.set(this.errMsg(error, 'Could not list tenants'));
      },
    });
  }

  protected createTenant(): void {
    const slug = this.tenantSlug.trim();
    const name = this.tenantName.trim();
    if (!slug || !name) {
      this.error.set('Tenant slug and name are required');
      return;
    }
    this.secureBusy.set(true);
    this.error.set(null);
    this.secure.createTenant(slug, name).subscribe({
      next: ({ tenant }) => {
        this.secureBusy.set(false);
        this.tenants.update((current) =>
          current.some(({ id }) => id === tenant.id) ? current : [tenant, ...current],
        );
        this.selectTenant(tenant.id);
        this.refreshTenants();
      },
      error: (error: unknown) => {
        this.secureBusy.set(false);
        this.error.set(this.errMsg(error, 'Create tenant failed'));
      },
    });
  }

  protected selectTenant(id: string): void {
    if (!this.tenants().some((tenant) => tenant.id === id)) return;
    this.activeTenantId.set(id);
    this.realtimeEvents.set([]);
    this.unsubscribeRealtime?.();
    this.unsubscribeRealtime = this.supabase.subscribeTelemetry(id, (row) => {
      this.realtimeEvents.update((previous) => [row, ...previous].slice(0, 10));
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
    let rawKey: Uint8Array | null = null;
    try {
      const identity = await generateX25519KeyPair();
      const peer = await generateX25519KeyPair();
      const sessionId = `browser-${crypto.randomUUID()}`;
      await firstValueFrom(
        this.secure.upsertSession({
          tenantId,
          sessionId,
          identityPublicKey: identity.publicKeyB64,
          ephemeralPublicKey: peer.publicKeyB64,
        }),
      );

      rawKey = await deriveSessionKeyRaw(identity.privateKey, peer.publicKey, sessionId);
      const key = await importAesKeyRaw(rawKey);
      const clientEventId = crypto.randomUUID();
      const envelope = await seal(
        JSON.stringify({ kind: 'event.poc', values: [1, 2, 3, 5, 8], ts: Date.now() }),
        { key, keyId: sessionId, tenantId, clientEventId },
      );
      const result = await firstValueFrom(
        this.secure.ingestSealed({
          tenantId,
          clientEventId,
          envelope,
          metadata: { source: 'angular-console' },
        }),
      );
      this.ingestResult.set(result);
    } catch (error: unknown) {
      this.error.set(this.errMsg(error, 'Secure ingest failed'));
    } finally {
      rawKey?.fill(0);
      this.secureBusy.set(false);
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

  private errMsg(error: unknown, fallback: string): string {
    if (error && typeof error === 'object') {
      if (
        'error' in error &&
        error.error &&
        typeof error.error === 'object' &&
        'detail' in error.error
      ) {
        return String((error.error as { detail: unknown }).detail);
      }
      if ('message' in error) return String((error as { message: unknown }).message);
    }
    return fallback;
  }
}
