/**
 * API client for the LLM Council backend (AWS deployment).
 * Uses async pattern: POST to submit, then poll GET for result.
 */

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
} from 'amazon-cognito-identity-js';

const API_BASE = 'https://4961isq9v3.execute-api.us-east-1.amazonaws.com/prod';

const poolData = {
  UserPoolId: 'us-east-1_b6MVS7S94',
  ClientId: '4j5kv8u1h8qk3bao1063mfin0a',
};

const userPool = new CognitoUserPool(poolData);

function getIdToken() {
  const user = userPool.getCurrentUser();
  return new Promise((resolve, reject) => {
    if (!user) return resolve(null);
    user.getSession((err, session) => {
      if (err) return reject(err);
      if (!session.isValid()) return resolve(null);
      resolve(session.getIdToken().getJwtToken());
    });
  });
}

export function signIn(email, password) {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: userPool });
    const authDetails = new AuthenticationDetails({ Username: email, Password: password });
    user.authenticateUser(authDetails, {
      onSuccess: (session) => resolve(session),
      onFailure: (err) => reject(err),
      newPasswordRequired: (userAttributes) => {
        delete userAttributes.email_verified;
        delete userAttributes.email;
        resolve({ newPasswordRequired: true, user, userAttributes });
      },
    });
  });
}

export function signUp(email, password) {
  return new Promise((resolve, reject) => {
    userPool.signUp(email, password, [], null, (err, result) => {
      if (err) return reject(err);
      resolve(result);
    });
  });
}

export function confirmSignUp(email, code) {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: userPool });
    user.confirmRegistration(code, true, (err, result) => {
      if (err) return reject(err);
      resolve(result);
    });
  });
}

export function signOut() {
  const user = userPool.getCurrentUser();
  if (user) user.signOut();
}

export async function isSignedIn() {
  try {
    const token = await getIdToken();
    return token !== null;
  } catch {
    return false;
  }
}

export function getCurrentUserEmail() {
  const user = userPool.getCurrentUser();
  return user ? user.getUsername() : null;
}

/**
 * Poll for a result until it's COMPLETE or FAILED.
 */
async function pollForResult(requestId, onStatus) {
  const token = await getIdToken();
  const maxAttempts = 60; // 60 × 5s = 300s max wait
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, 5000));

    const resp = await fetch(`${API_BASE}/council/${requestId}`, {
      headers: { Authorization: token },
    });

    if (!resp.ok) {
      throw new Error(`Poll failed (${resp.status})`);
    }

    const data = await resp.json();
    if (onStatus) onStatus(data.status);

    if (data.status === 'COMPLETE') {
      // result is stored as JSON string in DynamoDB
      return typeof data.result === 'string' ? JSON.parse(data.result) : data.result;
    }
    if (data.status === 'FAILED') {
      throw new Error(data.error || 'Council processing failed');
    }
    // PENDING or PROCESSING — keep polling
  }
  throw new Error('Timeout waiting for council response');
}

export const api = {
  /**
   * Send a message to the LLM Council (async: submit + poll).
   */
  async sendMessage(conversationId, content, onStatus) {
    const token = await getIdToken();
    if (!token) throw new Error('Not signed in');

    // Submit the request
    const submitResp = await fetch(`${API_BASE}/council`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: token,
      },
      body: JSON.stringify({
        prompt: content,
        session_id: conversationId,
      }),
    });

    if (!submitResp.ok) {
      const text = await submitResp.text();
      throw new Error(`Submit failed (${submitResp.status}): ${text}`);
    }

    const { requestId } = await submitResp.json();

    // Poll for the result
    return pollForResult(requestId, onStatus);
  },
};
