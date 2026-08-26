import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  getModeratorSession,
  logoutModerator,
  type ModeratorSession,
} from "../api/auth";

type SessionContextValue = {
  session: ModeratorSession | null;
  loading: boolean;
  setAuthenticatedSession: (session: ModeratorSession) => void;
  refreshSession: () => Promise<void>;
  logout: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<ModeratorSession | null>(null);
  const [loading, setLoading] = useState(true);

  async function refreshSession() {
    try {
      setSession(await getModeratorSession());
    } catch {
      setSession(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshSession();
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      loading,
      setAuthenticatedSession: setSession,
      refreshSession,
      logout: async () => {
        await logoutModerator();
        setSession(null);
      },
    }),
    [session, loading],
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (context === null) {
    throw new Error("useSession must be used inside SessionProvider");
  }
  return context;
}
