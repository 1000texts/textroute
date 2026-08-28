import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { SessionProvider, useSession } from "./auth/SessionContext";
import { AddMember } from "./pages/AddMember";
import { CreateGroup } from "./pages/CreateGroup";
import { GroupSettings } from "./pages/GroupSettings";
import { Login } from "./pages/Login";
import { Members } from "./pages/Members";
import { Messages } from "./pages/Messages";
import "./index.css";

function AppRoutes() {
  const navigate = useNavigate();
  const { session, logout } = useSession();

  return (
    <>
      <nav className="top-nav">
        <NavLink
          className={({ isActive }) =>
            isActive ? "nav-link active" : "nav-link"
          }
          to="/"
        >
          Create group
        </NavLink>
        {session ? (
          <>
            <NavLink
              className={({ isActive }) =>
                isActive ? "nav-link active" : "nav-link"
              }
              to="/messages"
            >
              Messages
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                isActive ? "nav-link active" : "nav-link"
              }
              to="/members"
            >
              Members
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                isActive ? "nav-link active" : "nav-link"
              }
              to="/add-member"
            >
              Add members
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                isActive ? "nav-link active" : "nav-link"
              }
              to="/settings"
            >
              Settings
            </NavLink>
            <button
              type="button"
              className="nav-link"
              onClick={async () => {
                await logout();
                navigate("/login", { replace: true });
              }}
            >
              Log out
            </button>
          </>
        ) : (
          <NavLink
            className={({ isActive }) =>
              isActive ? "nav-link active" : "nav-link"
            }
            to="/login"
          >
            Moderator login
          </NavLink>
        )}
      </nav>
      <Routes>
        <Route path="/" element={<CreateGroup />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/messages"
          element={
            <ProtectedRoute>
              <Messages />
            </ProtectedRoute>
          }
        />
        {/* The review queue is now a tab inside Messages. */}
        <Route path="/review" element={<Navigate to="/messages" replace />} />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <GroupSettings />
            </ProtectedRoute>
          }
        />
        <Route
          path="/members"
          element={
            <ProtectedRoute>
              <Members />
            </ProtectedRoute>
          }
        />
        <Route
          path="/add-member"
          element={
            <ProtectedRoute>
              <AddMember />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <AppRoutes />
      </SessionProvider>
    </BrowserRouter>
  );
}
