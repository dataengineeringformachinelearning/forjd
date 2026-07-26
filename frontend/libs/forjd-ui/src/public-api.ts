/*
 * Public API — forjd-ui suite adapter (Pass 2).
 * Chrome: vendored suite-tokens.css + suite-components.css
 * Docs:
 *   libs/forjd-ui/COMPONENTS.md          — props, outputs, usage patterns
 *   libs/forjd-ui/src/lib/styles/SUITE_COMPONENTS.md — CSS contracts
 *   docs/SUITE_UI_UNIFICATION.md
 *
 * Layout (feature groups — import only via this barrel from the app):
 *   core/     framework-neutral a11y + theme helpers
 *   chrome/   Angular theme service / toggle
 *   forms/    buttons + field controls
 *   overlay/  dialog, sheet, toast, search, preferences
 *   feedback/ status / empty / loading / onboarding
 *   data/     table, tabs, lists
 *   layout/   page shell, nav, cards
 *   styles/   synced suite CSS (do not relocate)
 *
 * Export order mirrors feature groups. Core helpers: uid → field-a11y → focus →
 * dialog-session → toast-store → optimistic → theme.
 */

// --- core ---
export { createUidFactory, forjdUid } from './lib/core/a11y/uid';
export {
  FIELD_CONTROL_SELECTOR,
  fieldDescribedBy,
  findFieldControl,
  syncFieldControlA11y,
} from './lib/core/a11y/field-a11y';
export type { FieldMessageIds } from './lib/core/a11y/field-a11y';
export {
  captureReturnFocus,
  focusFirst,
  getFocusableElements,
  isFocusable,
  nextRovingIndex,
  nextRovingIndexBothAxes,
  nextRovingIndexHorizontal,
  restoreFocus,
  trapTabKey,
} from './lib/core/a11y/focus';
export { NativeDialogSession } from './lib/core/a11y/dialog-session';
export { createToastStore } from './lib/core/a11y/toast-store';
export type { ToastStore } from './lib/core/a11y/toast-store';
export { runOptimistic } from './lib/core/a11y/optimistic';
export type { OptimisticResult, RunOptimisticOptions } from './lib/core/a11y/optimistic';
export {
  bindCommandHistoryShortcuts,
  createCommandHistory,
  getDefaultCommandHistory,
} from './lib/core/a11y/command-history';
export type {
  CommandHistory,
  CreateCommandHistoryOptions,
  HistoryEntry,
  RunHistoryCommand,
} from './lib/core/a11y/command-history';
export { createSelectionModel } from './lib/core/a11y/selection-model';
export type { CreateSelectionModelOptions, SelectionModel } from './lib/core/a11y/selection-model';
export {
  SUITE_DISCLOSURE_STORAGE_KEY,
  createDisclosureStore,
  getDefaultDisclosureStore,
  resetDefaultDisclosureStore,
} from './lib/core/a11y/disclosure';
export type { CreateDisclosureStoreOptions, DisclosureStore } from './lib/core/a11y/disclosure';
export {
  bindShortcutHelpKey,
  createShortcutRegistry,
  formatShortcutChord,
  getDefaultShortcutRegistry,
  isEditableKeyboardTarget,
  prefersMacModKey,
  resetDefaultShortcutRegistry,
  suiteDefaultShortcuts,
} from './lib/core/a11y/keyboard-shortcuts';
export type {
  CreateShortcutRegistryOptions,
  ShortcutRegistry,
  SuiteShortcut,
} from './lib/core/a11y/keyboard-shortcuts';
export {
  SUITE_PREFERENCES_CHANGE_EVENT,
  SUITE_PREFERENCES_STORAGE_KEY,
  createPreferencesStore,
  getDefaultPreferencesStore,
  resetDefaultPreferencesStore,
} from './lib/core/a11y/preferences';
export type {
  CreatePreferencesStoreOptions,
  PreferencesPatch,
  PreferencesStore,
  SuitePreferences,
} from './lib/core/a11y/preferences';
export {
  SUITE_EMPTY_GUIDANCE_EYEBROW,
  SUITE_ONBOARDING_CHANGE_EVENT,
  SUITE_ONBOARDING_STORAGE_KEY,
  createOnboardingStore,
  getDefaultOnboardingStore,
  resetDefaultOnboardingStore,
} from './lib/core/a11y/onboarding';
export type {
  CreateOnboardingStoreOptions,
  OnboardingStore,
  SuiteOnboardingFlow,
  SuiteOnboardingState,
} from './lib/core/a11y/onboarding';
export {
  SUITE_DATA_PACK_KIND,
  SUITE_DATA_PACK_VERSION,
  applySuiteDataPack,
  downloadSuiteDataPack,
  exportSuiteDataPack,
  parseSuiteDataPack,
  readSuiteDataPackFile,
} from './lib/core/a11y/suite-data-pack';
export type {
  ApplySuiteDataPackResult,
  ExportSuiteDataPackOptions,
  ImportSuiteDataPackOptions,
  ParseSuiteDataPackResult,
  SuiteDataPackV1,
} from './lib/core/a11y/suite-data-pack';
export {
  SUITE_ACTIVITY_CHANGE_EVENT,
  SUITE_ACTIVITY_STORAGE_KEY,
  createActivityLog,
  getDefaultActivityLog,
  recordSuiteActivity,
  resetDefaultActivityLog,
} from './lib/core/a11y/activity-log';
export type {
  ActivityLog,
  ActivityLogRecordInput,
  CreateActivityLogOptions,
  SuiteActivityEntry,
  SuiteActivitySource,
} from './lib/core/a11y/activity-log';
export { safeHref, safeHttpBase } from './lib/core/a11y/safe-href';
export type { SafeHrefOptions } from './lib/core/a11y/safe-href';
export { encodeForHtml, sanitizeDisplayText } from './lib/core/a11y/sanitize-text';
export type { SanitizeTextOptions } from './lib/core/a11y/sanitize-text';
export {
  SUITE_THEME_CHANGE_EVENT,
  SUITE_THEME_STORAGE_KEY,
  applySuiteTheme,
  cycleSuiteThemePreference,
  dispatchSuiteThemeChange,
  parseSuiteThemePreference,
  prefersDarkScheme,
  prefersReducedMotion,
  readSuiteThemePreference,
  resolveSuiteTheme,
  suiteThemeToggleAriaLabel,
  toggleSuiteThemePreference,
  writeSuiteThemePreference,
} from './lib/core/a11y/theme';
export type { SuiteThemePreference, SuiteThemeResolved } from './lib/core/a11y/theme';

// --- chrome ---
export { FjThemeService } from './lib/chrome/theme/theme.service';
export { FjThemeToggle } from './lib/chrome/theme/theme-toggle';
export { FjCommandHistoryService } from './lib/chrome/history/command-history.service';
export { FjShortcutHelpService } from './lib/chrome/shortcuts/shortcut-help.service';
export { FjPreferencesService } from './lib/chrome/preferences/preferences.service';

// --- forms ---
export { FjButton } from './lib/forms/button/button';
export type { FjButtonVariant } from './lib/forms/button/button';
export { FjField } from './lib/forms/field/field';
export { FjInput } from './lib/forms/input/input';
export { FjTextarea } from './lib/forms/textarea/textarea';
export { FjSelect } from './lib/forms/select/select';
export type { FjSelectOption } from './lib/forms/select/select';
export { FjCheckbox } from './lib/forms/checkbox/checkbox';
export { FjSwitch } from './lib/forms/switch/switch';

// --- overlay ---
export { FjDialog } from './lib/overlay/dialog/dialog';
export { FjSheet } from './lib/overlay/sheet/sheet';
export { FjToastHost, FjToastService } from './lib/overlay/toast/toast';
export type {
  FjToastAction,
  FjToastMessage,
  FjToastPriority,
  FjToastShowOptions,
  FjToastTone,
} from './lib/overlay/toast/toast';
export {
  defaultToastDurationMs,
  toastPriorityFromTone,
  toastPriorityRank,
} from './lib/core/a11y/toast-store';
export type { ToastPriority, ToastStoreItem } from './lib/core/a11y/toast-store';
export { restoreRecentSearches } from './lib/overlay/search-palette/recent-searches';
export { FjSearchPalette } from './lib/overlay/search-palette/search-palette';
export type { FjSearchPaletteItem } from './lib/overlay/search-palette/search-palette.types';
export { FjShortcutHelp } from './lib/overlay/shortcut-help/shortcut-help';
export { FjPreferencesPanel } from './lib/overlay/preferences/preferences-panel';
export { FjPreferences } from './lib/overlay/preferences/preferences-sheet';
export { rankSearchItems, scoreSearchItem } from './lib/overlay/search-palette/rank-search';
export {
  DEFAULT_RECENT_LIMIT,
  DEFAULT_RECENT_STORAGE_KEY,
  clearRecentSearches,
  pushRecentSearch,
  readRecentSearches,
  recentSearchesAsItems,
} from './lib/overlay/search-palette/recent-searches';
export type { FjRecentSearch } from './lib/overlay/search-palette/recent-searches';

// --- feedback ---
export { FjBadge } from './lib/feedback/badge/badge';
export type { FjTone, VikingTone } from './lib/feedback/badge/tones';
export { FjCallout } from './lib/feedback/callout/callout';
export { FjSkeleton } from './lib/feedback/skeleton/skeleton';
export { FjPageSkeleton } from './lib/feedback/page-skeleton/page-skeleton';
export type { FjPageSkeletonLayout } from './lib/feedback/page-skeleton/page-skeleton';
export { FjEmpty } from './lib/feedback/empty/empty';
export { FjErrorState } from './lib/feedback/error-state/error-state';
export { FjErrorBoundary } from './lib/feedback/error-boundary/error-boundary';
export { FjLoading, FjLoadingOverlay } from './lib/feedback/loading/loading';
export { FjDisclosure } from './lib/feedback/disclosure/disclosure';
export { FjOnboardingChecklist } from './lib/feedback/onboarding-checklist/onboarding-checklist';
export type { FjOnboardingStep } from './lib/feedback/onboarding-checklist/onboarding-checklist';
export { FjStreamStatus } from './lib/feedback/stream-status/stream-status';
export type {
  FjStreamStatusPhase,
  FjStreamStatusTone,
} from './lib/feedback/stream-status/stream-status';

// --- data ---
export { FjTabs } from './lib/data/tabs/tabs';
export type { FjTabItem } from './lib/data/tabs/tabs';
export { FjTabPanel } from './lib/data/tabs/tab-panel';
export { FjBulkToolbar } from './lib/data/bulk-toolbar/bulk-toolbar';
export type { FjBulkAction } from './lib/data/bulk-toolbar/bulk-toolbar';
export { FjTable } from './lib/data/table/table';
export type { FjTableCellValue, FjTableColumn, FjTableRow } from './lib/data/table/table';
export { FjVirtualList } from './lib/data/virtual-list/virtual-list';
export type {
  FjVirtualListItem,
  FjVirtualListItemContext,
} from './lib/data/virtual-list/virtual-list';
export { computeVirtualWindow, indicesForWindow } from './lib/data/virtual-list/virtual-window';
export type { FjVirtualWindow, FjVirtualWindowInput } from './lib/data/virtual-list/virtual-window';
export { FjStatusList } from './lib/data/status-list/status-list';
export type { FjStatusItem } from './lib/data/status-list/status-list';
export { FjActivityList } from './lib/data/activity-list/activity-list';
export { FjPipelineFlow } from './lib/data/pipeline-flow/pipeline-flow';
export type { FjPipelineStep } from './lib/data/pipeline-flow/pipeline-flow';

// --- layout ---
export { FjPageShell, FjSection, FjStack } from './lib/layout/page-shell/page-shell';
export type { FjLayoutDensity } from './lib/layout/page-shell/page-shell';
export { FjNav } from './lib/layout/nav/nav';
export type { FjNavItem } from './lib/layout/nav/nav';
export { FjCard } from './lib/layout/card/card';
export { FjPanel } from './lib/layout/panel/panel';
export { FjAvatar } from './lib/layout/avatar/avatar';
export { FjSeparator } from './lib/layout/separator/separator';
