import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import RagEvalApp from "./RagEvalApp.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <RagEvalApp />
  </StrictMode>,
);
