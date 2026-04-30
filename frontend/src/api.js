/**
 * API client for the LLM Council backend (AWS deployment).
 * Authenticates via Cognito and calls API Gateway.
 */

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
} from 'amazon-cognito-identity-js';

const API_BASE = 'https://ici6ra5fdvk2sxonxnu4rsormu0lwhhr.lambda-url.us-east-1.on.aws';

const poolData = {
  UserPoolId: 'us-east-1_b6MVS7S94',
  ClientId: '4j5kv8u1h8qk3bao1063mfin0a',
};

const userPool = new CognitoUserPool(poolData);

/**
 * Get the current user's ID token, or null if not signed in.
 */
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

/**
 * Sign in a user with email and password.
 */
export function signIn(email, password) {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({
      Username: email,
      Pool: userPool,
    });
    const authDetails = new AuthenticationDetails({
      Username: email,
      Password: password,
    });
    user.authenticateUser(authDetails, {
      onSuccess: (session) => resolve(session),
      onFailure: (err) => reject(err),
      newPasswordRequired: (userAttributes) => {
        // First-time login with temp password — force change
        delete userAttributes.email_verified;
        delete userAttributes.email;
        resolve({ newPasswordRequired: true, user, userAttributes });
      },
    });
  });
}

/**
 * Sign up a new user.
 */
export function signUp(email, password) {
  return new Promise((resolve, reject) => {
    userPool.signUp(email, password, [], null, (err, result) => {
      if (err) return reject(err);
      resolve(result);
    });
  });
}

/**
 * Confirm sign-up with verification code.
 */
export function confirmSignUp(email, code) {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: userPool });
    user.confirmRegistration(code, true, (err, result) => {
      if (err) return reject(err);
      resolve(result);
    });
  });
}

/**
 * Sign out the current user.
 */
export function signOut() {
  const user = userPool.getCurrentUser();
  if (user) user.signOut();
}

/**
 * Check if a user is currently signed in.
 */
export async function isSignedIn() {
  try {
    const token = await getIdToken();
    return token !== null;
  } catch {
    return false;
  }
}

/**
 * Get the current user's email.
 */
export function getCurrentUserEmail() {
  const user = userPool.getCurrentUser();
  return user ? user.getUsername() : null;
}

export const api = {
  /**
   * Send a message to the LLM Council.
   */
  async sendMessage(conversationId, content) {
    const token = await getIdToken();
    if (!token) {
      throw new Error('Not signed in');
    }

    const response = await fetch(API_BASE, {
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

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Request failed (${response.status}): ${text}`);
    }

    return response.json();
  },
};
