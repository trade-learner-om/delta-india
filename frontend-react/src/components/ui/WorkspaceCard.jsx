import { card } from "../../utils/workspace/workspaceClasses";

export default function WorkspaceCard({ children, className = "", padding = "p-5" }) {
  return <div className={`${card(padding)} ${className}`.trim()}>{children}</div>;
}
