import { createContext, useContext } from "react";

const StreamProgressContext = createContext(null);

export function StreamProgressProvider({ value, children }) {
  return <StreamProgressContext.Provider value={value}>{children}</StreamProgressContext.Provider>;
}

export function useStreamProgress() {
  return useContext(StreamProgressContext);
}
