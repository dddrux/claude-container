// patchMob.1: vaca-cogumelo (M_MOOSH) = partes/IA/drops da vaca + patchPerf.1 (cache de bioma com seed de 64 bits). Roda o main.cpp REAL.
#include <unistd.h>
#define main game_main
#include "../src/main.cpp"
#undef main
void* SDL_GL_GetProcAddress(const char*) { return nullptr; }
Uint32 SDL_GetTicks() { static Uint32 t = 0; return t += 7; }
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; printf("  FALHOU linha %d: %s\n", __LINE__, #c); } } while (0)
int main() {
    WORLD_SEED = -3593944369965200562LL;   // seed que nao cabe em 32 bits: antes o cache de bioma era limpo a cada chamada
    float g[3], l[3]; biomeTints(500.f, 700.f, g, l); const size_t n0 = gBioRaw.size(); biomeTints(501.f, 701.f, g, l);
    CHECK(n0 > 0 && gBioRaw.size() >= n0 && gBioRawSeed == (int64_t)WORLD_SEED);
    CHECK(M_MOOSH < M_N && std::string(MD[M_MOOSH].nome) == "vaca-cogumelo");   // patchFix.15: nao e mais o ultimo tipo (M_SLIME entrou depois)
    for (int cz = -1; cz <= 1; cz++) for (int cx = -1; cx <= 1; cx++) if (!getC(cx, cz)) gen(cx, cz);
    const size_t m0 = MOBS.size(); spawnMob(M_MOOSH, 4.5, 100, 4.5, 0.f); CHECK(MOBS.size() == m0 + 1 && MOBS.back().type == M_MOOSH && MOBS.back().hp == 10);
    CHECK(mobSndFor(M_MOOSH) != nullptr);
    // patchBio.2: grade de bioma suave: cantos vizinhos quase iguais e biomeTints continua nos cantos
    { const BTGrid& G = biomeGrid(31, 43); float mx = 0; for (int gz = 0; gz <= 16; gz++) for (int gx = 0; gx < 16; gx++) for (int q = 0; q < 3; q++) mx = std::max(mx, fabsf(G.g[gz * 17 + gx + 1][q] - G.g[gz * 17 + gx][q]));
      CHECK(mx < .08f); float a[3], b[3]; biomeTints(31 * 16 + 5.f, 43 * 16 + 7.f, a, b); CHECK(fabsf(a[1] - G.g[7 * 17 + 5][1]) < 1e-4f); }
    printf("%d verificacoes, %d falhas\n", checks, fails); return fails ? 1 : 0;
}
