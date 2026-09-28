import { Suspense } from "react";
import { WorkflowList } from "@/components/workflow-list";
import { Loading } from "@/components/ui";
export default function Workflows() {
  return (
    <Suspense fallback={<Loading />}>
      <WorkflowList />
    </Suspense>
  );
}
