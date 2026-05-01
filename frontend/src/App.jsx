import { useState, useEffect } from 'react';
import ChatInterface from './components/ChatInterface';
import { api, signIn, signUp, confirmSignUp, signOut, isSignedIn, getCurrentUserEmail } from './api';
import './App.css';

function AuthScreen({ onSignedIn }) {
  const [mode, setMode] = useState('signin'); // signin | signup | confirm
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSignIn = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result = await signIn(email, password);
      if (result.newPasswordRequired) {
        setError('Please contact your administrator — a password reset is required.');
      } else {
        onSignedIn();
      }
    } catch (err) {
      setError(err.message || 'Sign in failed');
    }
    setLoading(false);
  };

  const handleSignUp = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await signUp(email, password);
      setMode('confirm');
    } catch (err) {
      setError(err.message || 'Sign up failed');
    }
    setLoading(false);
  };

  const handleConfirm = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await confirmSignUp(email, code);
      // Auto sign in after confirmation
      await signIn(email, password);
      onSignedIn();
    } catch (err) {
      setError(err.message || 'Confirmation failed');
    }
    setLoading(false);
  };

  return (
    <div className="auth-screen">
      <div className="auth-box">
        <h1>LLM Council</h1>
        <p className="auth-subtitle">Sign in to consult the council</p>

        {error && <div className="auth-error">{error}</div>}

        {mode === 'signin' && (
          <form onSubmit={handleSignIn}>
            <input type="email" placeholder="Email" value={email}
              onChange={(e) => setEmail(e.target.value)} required />
            <input type="password" placeholder="Password" value={password}
              onChange={(e) => setPassword(e.target.value)} required />
            <button type="submit" disabled={loading}>
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
            <p className="auth-switch">
              No account? <span onClick={() => setMode('signup')}>Sign up</span>
            </p>
          </form>
        )}

        {mode === 'signup' && (
          <form onSubmit={handleSignUp}>
            <input type="email" placeholder="Email" value={email}
              onChange={(e) => setEmail(e.target.value)} required />
            <input type="password" placeholder="Password (min 8 chars)" value={password}
              onChange={(e) => setPassword(e.target.value)} required minLength={8} />
            <button type="submit" disabled={loading}>
              {loading ? 'Creating account...' : 'Sign Up'}
            </button>
            <p className="auth-switch">
              Have an account? <span onClick={() => setMode('signin')}>Sign in</span>
            </p>
          </form>
        )}

        {mode === 'confirm' && (
          <form onSubmit={handleConfirm}>
            <p>Check your email for a verification code.</p>
            <input type="text" placeholder="Verification code" value={code}
              onChange={(e) => setCode(e.target.value)} required />
            <button type="submit" disabled={loading}>
              {loading ? 'Verifying...' : 'Verify'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}


function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);
  const [conversation, setConversation] = useState({
    id: 'council-' + Date.now(),
    messages: [],
  });
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    isSignedIn().then((yes) => {
      setAuthenticated(yes);
      setChecking(false);
    });
  }, []);

  const handleSignOut = () => {
    signOut();
    setAuthenticated(false);
  };

  const handleSendMessage = async (content) => {
    setIsLoading(true);

    // Add user message
    const userMsg = { role: 'user', content };
    setConversation((prev) => ({
      ...prev,
      messages: [...prev.messages, userMsg],
    }));

    // Add loading assistant message
    const loadingMsg = {
      role: 'assistant',
      stage1: null, stage2: null, stage3: null, metadata: null,
      loading: { stage1: true, stage2: true, stage3: true },
    };
    setConversation((prev) => ({
      ...prev,
      messages: [...prev.messages, loadingMsg],
    }));

    try {
      const result = await api.sendMessage(conversation.id, content);
      console.log('Council result:', result);
      const structured = result.structured || result;
      console.log('Structured:', structured);

      // Replace loading message with real data
      setConversation((prev) => {
        const msgs = [...prev.messages];
        msgs[msgs.length - 1] = {
          role: 'assistant',
          stage1: structured.stage1 || [],
          stage2: structured.stage2 || [],
          stage3: structured.stage3 || {},
          metadata: structured.metadata || {},
          loading: { stage1: false, stage2: false, stage3: false },
        };
        return { ...prev, messages: msgs };
      });
    } catch (err) {
      console.error('Council error:', err);
      // Show error to user instead of silently removing
      setConversation((prev) => {
        const msgs = [...prev.messages];
        msgs[msgs.length - 1] = {
          role: 'assistant',
          stage1: null,
          stage2: null,
          stage3: { model: 'error', display_name: 'Error', response: err.message },
          metadata: null,
          loading: { stage1: false, stage2: false, stage3: false },
        };
        return { ...prev, messages: msgs };
      });
    }

    setIsLoading(false);
  };

  if (checking) {
    return <div className="app loading-screen">Loading...</div>;
  }

  if (!authenticated) {
    return <AuthScreen onSignedIn={() => setAuthenticated(true)} />;
  }

  return (
    <div className="app">
      <div className="top-bar">
        <span className="top-bar-title">LLM Council</span>
        <span className="top-bar-user">{getCurrentUserEmail()}</span>
        <button className="sign-out-btn" onClick={handleSignOut}>Sign Out</button>
      </div>
      <ChatInterface
        conversation={conversation}
        onSendMessage={handleSendMessage}
        isLoading={isLoading}
      />
    </div>
  );
}

export default App;
