export type Intent = 'find_recipe' | 'scale_recipe' | 'build_indent' | 'check_anomaly' | 'general'

export interface Source {
  recipe: string
  component: string
  file: string
}

export interface AnomalyResult {
  ingredient: string
  component: string
  recipe: string
  actual_g: number
  min_g: number
  max_g: number
  passed: boolean
  advice: string
}

export interface AnomalyReport {
  recipe_name: string
  results: AnomalyResult[]
  overall_pass: boolean
}

export interface ScaledIngredient {
  name: string
  original_qty_g: number
  scaled_qty_g: number
  non_linear_warning: boolean
}

export interface ScaleResult {
  recipe_name: string
  component_name: string
  original_yield: number
  target_yield: number
  scale_factor: number
  scaled_ingredients: ScaledIngredient[]
  warnings: string[]
}

export interface IndentRow {
  ingredient: string
  category: string
  total_qty_g: number
  sources: string[]
}

export interface IndentSheet {
  recipes: string[]
  rows: IndentRow[]
}

export interface RecipeIngredient {
  name: string
  qty_g: number
  pct: number | null
}

export interface RecipeComponent {
  component_name: string
  yield_label: string
  ingredients: RecipeIngredient[]
  total_g: number
  method: string[]
  method_raw: string
}

export interface RecipeData {
  recipe_name: string
  source_file: string
  section?: string
  components: RecipeComponent[]
}

export type StructuredResult =
  | { type: 'anomaly_report'; data: AnomalyReport }
  | { type: 'scale_results'; data: ScaleResult[] }
  | { type: 'indent_sheet'; data: IndentSheet }
  | { type: 'recipe_results'; data: { recipes: RecipeData[] } }

export interface MessageMeta {
  confidence: number
  intent: Intent | ''
  sources: Source[]
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  structuredResult?: StructuredResult
  meta?: MessageMeta
  statusSteps?: string[]
  streaming?: boolean
}

export interface Stats {
  pinecone_vectors: number
  bm25_chunks: number
}
