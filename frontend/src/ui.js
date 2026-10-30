import { createContext, useContext } from "react";

// Shared across tabs: open a bottom sheet, show a toast, jump to a tab, current member + live data.
export const UI = createContext(null);
export const useUI = () => useContext(UI);
