// joystick estilo Bedrock: zona morta, 8 direcoes, correr na borda da frente, agachar no botao separado
#include <unistd.h>
#define main game_main
#include "../src/main.cpp"
#undef main
void* SDL_GL_GetProcAddress(const char*) { return nullptr; }
Uint32 SDL_GetTicks() { static Uint32 t = 0; return t += 7; }   // patchFix.15: touchEvent chama SDL_GetTicks (sem stub = chamada nula = segfault)
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; printf("  FALHOU linha %d: %s\n", __LINE__, #c); } } while (0)
static const int SW = 2400, SH = 1080;
static void fing(int type, int64_t id, float x, float y) { SDL_Event e; memset(&e, 0, sizeof e); e.type = type; e.tfinger.fingerId = id; e.tfinger.x = x / SW; e.tfinger.y = y / SH; touchEvent(e, SW, SH); }
int main() {   // patchFix.15: o joystick analogico saiu no patchPE.1; o teste cobre o direcional estilo PE (dp: 0 frente, 1 tras, 2 esquerda, 3 direita, 4 agachar)
    touchHud = true; touchReset(); const TLay L = touchLay(SW, SH);
    auto dpx = [&](int i) { return L.dp[i].x + 5; }; auto dpy = [&](int i) { return L.dp[i].y + 5; };
    fing(SDL_FINGERDOWN, 1, dpx(0), dpy(0)); CHECK(tvF && !tvB && !tvL && !tvR);                      // seta da frente
    fing(SDL_FINGERMOTION, 1, dpx(3), dpy(3)); CHECK(tvR && !tvF);                                    // deslizar troca a direcao
    fing(SDL_FINGERMOTION, 1, dpx(2), dpy(2)); CHECK(tvL && !tvR);
    fing(SDL_FINGERMOTION, 1, dpx(1), dpy(1)); CHECK(tvB && !tvL);
    fing(SDL_FINGERUP, 1, 0, 0); CHECK(!tvF && !tvB && !tvL && !tvR && !tvSprint);                    // soltou = para
    const bool s0 = tvSneakT; fing(SDL_FINGERDOWN, 2, dpx(4), dpy(4)); CHECK(tvSneakT != s0); fing(SDL_FINGERUP, 2, 0, 0);   // centro = agachar (liga/desliga)
    fing(SDL_FINGERDOWN, 3, L.jump.x + 5, L.jump.y + 5); CHECK(tvJump); fing(SDL_FINGERUP, 3, 0, 0); CHECK(!tvJump);
    fing(SDL_FINGERDOWN, 4, dpx(0), dpy(0)); fing(SDL_FINGERDOWN, 5, L.jump.x + 5, L.jump.y + 5); CHECK(tvF && tvJump);   // multitoque
    printf("%d verificacoes, %d falhas\n", checks, fails); return fails != 0;
}
