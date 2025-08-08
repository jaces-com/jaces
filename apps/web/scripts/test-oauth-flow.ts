#!/usr/bin/env tsx

// Test what URL is actually being generated
const authProxyUrl = 'https://auth.jaces.com/google/auth';
const returnUrl = 'http://localhost:3000/oauth/callback';
const state = '/data/sources/new';

const oauthUrl = `${authProxyUrl}?return_url=${encodeURIComponent(returnUrl)}&state=${encodeURIComponent(state)}`;

console.log('OAuth URL that should be generated:');
console.log(oauthUrl);
console.log('\nDecoded parts:');
console.log('- return_url:', decodeURIComponent('http%3A%2F%2Flocalhost%3A3000%2Foauth%2Fcallback'));
console.log('- state:', decodeURIComponent('%2Fdata%2Fsources%2Fnew'));

// What the OAuth proxy should receive
console.log('\nOAuth proxy should receive:');
console.log('- return_url param:', returnUrl);
console.log('- state param:', state);

// What should be passed back to callback
console.log('\nCallback should receive:');
console.log('- state param:', state);
console.log('- Final redirect:', state + '?connected=google');