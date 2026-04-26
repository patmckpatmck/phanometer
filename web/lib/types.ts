// Shape of one daily record as emitted by phanometer.py into data/history.json.
// See ../../../README.md for the authoritative contract.

export type DimensionKey =
  | 'results_satisfaction'
  | 'front_office_trust'
  | 'manager_confidence'
  | 'lineup_confidence'
  | 'pitching_confidence'
  | 'health_outlook'
  | 'postseason_belief';

export type Dimensions = Record<DimensionKey, number>;
export type DimensionConfidence = Partial<Record<DimensionKey, number>>;

export type VoiceKey = 'reddit' | 'beat_writer' | 'fan_analyst' | 'radio_populist';

export interface Voice {
  score: number | null;
  note: string | null;
}

export type VoiceBreakdown = Record<VoiceKey, Voice>;

export interface Theme {
  name: string;
  delta: number;
  sample: string;
}

export interface Quote {
  text: string;
  score: number;
  source_hint: string;
}

export interface SourceCounts {
  reddit_posts?: number;
  reddit_comments?: number;
  match_threads?: number;
  podcasts_attempted?: number;
  podcasts_transcribed?: number;
  podcast_chars?: number;
  youtube_attempted?: number;
  youtube_transcribed?: number;
  youtube_chars?: number;
}

export interface PodcastUsed {
  feed_name: string;
  title: string;
  voice: VoiceKey;
  chars: number;
}

export interface AttendanceGame {
  game_pk: number;
  date: string;
  day_of_week: string;
  opponent: string;
  result: string;
  attendance: number;
  pct_capacity: number;
  day_night: 'day' | 'night';
}

export type AttendanceStatus = 'ok' | 'error' | 'no_recent_home_games' | 'insufficient_data';

export interface AttendanceOk {
  status: 'ok';
  capacity: number;
  recent_window_days: number;
  baseline_source: string;
  recent_games_count: number;
  recent_avg_pct: number;
  baseline_games_count: number;
  baseline_avg_pct: number;
  delta_pct: number;
  canary_signal: boolean;
  recent_games: AttendanceGame[];
}

export interface AttendanceMissing {
  status: Exclude<AttendanceStatus, 'ok'>;
  recent_window_days?: number;
  error?: string;
  recent_games?: AttendanceGame[];
}

export type Attendance = AttendanceOk | AttendanceMissing;

export interface HardSignals {
  attendance?: Attendance;
}

export interface DailyReport {
  date: string;
  // Null on days flagged insufficient_signal — content volume fell below
  // MIN_CONTENT_VOLUME in phanometer.py. Mood label follows display_score.
  display_score: number | null;
  reactive_score: number;
  baseline_score: number | null;
  mood_label: string | null;
  // Optional: only written on records generated after 2026-04-23.
  insufficient_signal?: boolean;
  content_volume?: number;
  dimensions: Dimensions;
  dimension_confidence: DimensionConfidence;
  voice_breakdown: VoiceBreakdown;
  themes: Theme[];
  quotes: Quote[];
  // Optional: only written on records generated after 2026-04-26.
  vibe_summary?: string;
  reasoning: string;
  source_counts: SourceCounts;
  podcasts_used?: PodcastUsed[];
  hard_signals?: HardSignals;
  generated_at: string;
}

export function isAttendanceOk(a: Attendance | undefined): a is AttendanceOk {
  return a?.status === 'ok';
}
