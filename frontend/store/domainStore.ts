import { create } from 'zustand'

type Domain = { id?:string; name?:string };

type DomainState = {
  active?: Domain;
  setActive: (d?: Domain) => void;
};

export const useDomainStore = create<DomainState>((set) => ({
  active: undefined,
  setActive: (d) => set({ active: d }),
}));
