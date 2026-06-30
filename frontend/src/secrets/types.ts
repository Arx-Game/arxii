/** Character Secrets API types (#1334), from the generated OpenAPI schema. */
import type { components } from '@/generated/api';

export type KnownSecret = components['schemas']['KnownSecret'];
export type PaginatedKnownSecretList = components['schemas']['PaginatedKnownSecretList'];

/** A preset grievance response a wronged character may choose (#1429). */
export type GrievanceOption = components['schemas']['GrievanceOption'];

/** Gossip (#1572): a Level-1 secret you could spread + its heat in this region. */
export type GossipSecret = components['schemas']['GossipSecret'];
/** Outcome of a plant/seek/suppress gossip action (#1572). */
export type GossipResult = components['schemas']['GossipResult'];
