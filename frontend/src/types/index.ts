export interface Transaction {
  id: string;
  user_id: string;
  type: "deposit" | "withdraw";
  amount: number;
  status: string;
  reference?: string;
  created_at: string;
}

export interface WalletAction {
  user_id: string;
  amount: number;
  note?: string;
}
