import { useState } from "react";
import { CreateGroup } from "./pages/CreateGroup";
import { ReviewQueue } from "./pages/ReviewQueue";
import "./index.css";

type Page = "create" | "review";

export default function App() {
  const [page, setPage] = useState<Page>("review");

  return (
    <>
      <nav className="top-nav">
        <button
          type="button"
          className={page === "create" ? "nav-link active" : "nav-link"}
          onClick={() => setPage("create")}
        >
          Create group
        </button>
        <button
          type="button"
          className={page === "review" ? "nav-link active" : "nav-link"}
          onClick={() => setPage("review")}
        >
          Review
        </button>
      </nav>
      {page === "create" ? <CreateGroup /> : <ReviewQueue />}
    </>
  );
}
