/** Minimal type used by markdown-paper-parser (from gaokao-math-assistant). */
export interface ImportedQuestion {
  id: string;
  index: number;
  stemHtml: string;
  answerHtml: string;
  analysisHtml: string;
  detailHtml: string;
  stemText: string;
}
