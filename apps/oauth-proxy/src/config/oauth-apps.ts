import dotenv from 'dotenv';
import path from 'path';

// Load from the main .env file in the root directory
dotenv.config({ path: path.resolve(__dirname, '../../../../.env') });

// Debug: Check if env vars are loaded
console.log('Environment variables check:', {
  GOOGLE_CLIENT_ID: process.env.GOOGLE_CLIENT_ID ? 'LOADED' : 'NOT_LOADED',
  GOOGLE_CLIENT_SECRET: process.env.GOOGLE_CLIENT_SECRET ? 'LOADED' : 'NOT_LOADED',
  GOOGLE_REDIRECT_URI: process.env.GOOGLE_REDIRECT_URI || 'NOT_SET',
  NOTION_CLIENT_ID: process.env.NOTION_CLIENT_ID ? 'LOADED' : 'NOT_LOADED',
  NOTION_CLIENT_SECRET: process.env.NOTION_CLIENT_SECRET ? 'LOADED' : 'NOT_LOADED',
  STRAVA_CLIENT_ID: process.env.STRAVA_CLIENT_ID ? 'LOADED' : 'NOT_LOADED',
  STRAVA_CLIENT_SECRET: process.env.STRAVA_CLIENT_SECRET ? 'LOADED' : 'NOT_LOADED'
});

export interface OAuthConfig {
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  scopes: string[];
  authUrl: string;
  tokenUrl: string;
}

export const oauthConfigs = {
  google: {
    clientId: process.env.GOOGLE_CLIENT_ID || '',
    clientSecret: process.env.GOOGLE_CLIENT_SECRET || '',
    redirectUri: process.env.GOOGLE_REDIRECT_URI || 'https://auth.jaces.com/google/callback',
    scopes: [
      'https://www.googleapis.com/auth/calendar.readonly',
      'https://www.googleapis.com/auth/gmail.readonly',
      'https://www.googleapis.com/auth/drive.readonly'
    ],
    authUrl: 'https://accounts.google.com/o/oauth2/v2/auth',
    tokenUrl: 'https://oauth2.googleapis.com/token'
  },
  
  notion: {
    clientId: process.env.NOTION_CLIENT_ID || '',
    clientSecret: process.env.NOTION_CLIENT_SECRET || '',
    redirectUri: process.env.NOTION_REDIRECT_URI || 'https://auth.jaces.com/notion/callback',
    scopes: [], // Notion doesn't use scopes in OAuth URL
    authUrl: 'https://api.notion.com/v1/oauth/authorize',
    tokenUrl: 'https://api.notion.com/v1/oauth/token'
  },
  
  microsoft: {
    clientId: process.env.MICROSOFT_CLIENT_ID || '',
    clientSecret: process.env.MICROSOFT_CLIENT_SECRET || '',
    redirectUri: process.env.MICROSOFT_REDIRECT_URI || 'https://auth.jaces.com/microsoft/callback',
    scopes: [
      'https://graph.microsoft.com/calendars.read',
      'https://graph.microsoft.com/mail.read',
      'https://graph.microsoft.com/files.read'
    ],
    authUrl: 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
    tokenUrl: 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
  },
  
  github: {
    clientId: process.env.GITHUB_CLIENT_ID || '',
    clientSecret: process.env.GITHUB_CLIENT_SECRET || '',
    redirectUri: process.env.GITHUB_REDIRECT_URI || 'https://auth.jaces.com/github/callback',
    scopes: ['repo', 'user:email'],
    authUrl: 'https://github.com/login/oauth/authorize',
    tokenUrl: 'https://github.com/login/oauth/access_token'
  },
  
  strava: {
    clientId: process.env.STRAVA_CLIENT_ID || '',
    clientSecret: process.env.STRAVA_CLIENT_SECRET || '',
    redirectUri: process.env.STRAVA_REDIRECT_URI || 'https://auth.jaces.com/strava/callback',
    scopes: ['read,activity:read_all'], // Strava uses comma-separated scopes
    authUrl: 'https://www.strava.com/oauth/authorize',
    tokenUrl: 'https://www.strava.com/oauth/token'
  }
} as const;

export type OAuthProvider = keyof typeof oauthConfigs;