import type { VoiceKey } from './types';

export function formatDate(iso: string): string {
  const d = new Date(iso + 'T12:00:00');
  return d.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export function formatDateShort(iso: string): string {
  const d = new Date(iso + 'T12:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase();
}

export function formatTime(ts: string): string {
  const d = new Date(ts);
  return (
    d.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: 'America/New_York',
    }) + ' ET'
  );
}

const TEAM_CALLSIGN: Record<string, string> = {
  'Arizona Diamondbacks': 'AZ',
  'Atlanta Braves': 'ATL',
  'Baltimore Orioles': 'BAL',
  'Boston Red Sox': 'BOS',
  'Chicago Cubs': 'CHC',
  'Chicago White Sox': 'CWS',
  'Cincinnati Reds': 'CIN',
  'Cleveland Guardians': 'CLE',
  'Colorado Rockies': 'COL',
  'Detroit Tigers': 'DET',
  'Houston Astros': 'HOU',
  'Kansas City Royals': 'KC',
  'Los Angeles Angels': 'LAA',
  'Los Angeles Dodgers': 'LAD',
  'Miami Marlins': 'MIA',
  'Milwaukee Brewers': 'MIL',
  'Minnesota Twins': 'MIN',
  'New York Mets': 'NYM',
  'New York Yankees': 'NYY',
  Athletics: 'ATH',
  'Oakland Athletics': 'ATH',
  'Philadelphia Phillies': 'PHI',
  'Pittsburgh Pirates': 'PIT',
  'San Diego Padres': 'SD',
  'San Francisco Giants': 'SF',
  'Seattle Mariners': 'SEA',
  'St. Louis Cardinals': 'STL',
  'Tampa Bay Rays': 'TB',
  'Texas Rangers': 'TEX',
  'Toronto Blue Jays': 'TOR',
  'Washington Nationals': 'WSH',
};

export function teamCallsign(name: string | undefined): string {
  if (!name) return '';
  if (TEAM_CALLSIGN[name]) return TEAM_CALLSIGN[name];
  const last = name.split(' ').slice(-1)[0] ?? '';
  return last.slice(0, 3).toUpperCase();
}

export const VOICE_META: Record<VoiceKey, { name: string; pub?: string }> = {
  reddit: { name: 'r/phillies' },
  beat_writer: { name: 'Matt Gelb', pub: 'Phillies Therapy' },
  fan_analyst: { name: 'Hittin\u2019 Season', pub: 'podcast' },
  radio_populist: { name: 'WIP Daily', pub: '94WIP' },
};

export const DIM_LABELS: Record<string, string> = {
  results_satisfaction: 'Results satisfaction',
  front_office_trust: 'Front-office trust',
  manager_confidence: 'Manager confidence',
  lineup_confidence: 'Lineup confidence',
  pitching_confidence: 'Pitching confidence',
  health_outlook: 'Health outlook',
  postseason_belief: 'Postseason belief',
};

export const DIMENSION_ORDER = [
  'results_satisfaction',
  'pitching_confidence',
  'lineup_confidence',
  'health_outlook',
  'manager_confidence',
  'front_office_trust',
  'postseason_belief',
] as const;
