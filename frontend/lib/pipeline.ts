export function summarizePipeline(p:any){
  return { id: p?.id, tasks: p?.tasks?.length ?? 0 };
}
