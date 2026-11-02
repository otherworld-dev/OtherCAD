// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileCopyrightText: 2026 Joao Matos
// SPDX-FileNotice: Part of the FreeCAD project.

/******************************************************************************
 *                                                                            *
 *   FreeCAD is free software: you can redistribute it and/or modify          *
 *   it under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1            *
 *   of the License, or (at your option) any later version.                   *
 *                                                                            *
 *   FreeCAD is distributed in the hope that it will be useful,               *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty              *
 *   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                  *
 *   See the GNU Lesser General Public License for more details.              *
 *                                                                            *
 *   You should have received a copy of the GNU Lesser General Public         *
 *   License along with FreeCAD. If not, see https://www.gnu.org/licenses     *
 *                                                                            *
 ******************************************************************************/

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <thread>

#include <boost/scope_exit.hpp>
#include <gtest/gtest.h>

#include "App/Application.h"
#include "App/Document.h"
#include "App/FeatureTest.h"
#include "App/MainThreadSignal.h"
#include <src/App/InitApplication.h>

using namespace std::chrono_literals;

namespace
{

// Stands in for the GUI's main-thread hooks. Calls from other threads queue up
// until the test thread pumps them, like Qt's queued connections. A blocking
// hop that isn't serviced within hopTimeout runs on the calling thread instead
// and is counted, so a main thread that never services it fails the test
// rather than hanging it.
class FakeMainThread
{
public:
    static constexpr auto hopTimeout = 2s;

    FakeMainThread()
    {
        auto& s = state();
        {
            std::lock_guard<std::mutex> lock(s.mutex);
            s.mainThread = std::this_thread::get_id();
            s.queue.clear();
            s.timedOutHops = 0;
        }
        App::MainThreadSignalConfig::setHooks(&isMainThread, &invoke);
    }

    ~FakeMainThread()
    {
        pump();
        App::MainThreadSignalConfig::setHooks(nullptr, nullptr);
    }

    FakeMainThread(const FakeMainThread&) = delete;
    FakeMainThread& operator=(const FakeMainThread&) = delete;

    // Run everything queued for the main thread so far
    static void pump()
    {
        auto& s = state();
        for (;;) {
            std::shared_ptr<Hop> hop;
            {
                std::lock_guard<std::mutex> lock(s.mutex);
                if (s.queue.empty()) {
                    return;
                }
                hop = s.queue.front();
                s.queue.pop_front();
            }
            hop->fn();
            {
                std::lock_guard<std::mutex> lock(s.mutex);
                hop->done = true;
            }
            s.changed.notify_all();
        }
    }

    static bool pumpUntil(const std::function<bool()>& done, std::chrono::milliseconds timeout)
    {
        const auto deadline = std::chrono::steady_clock::now() + timeout;
        while (!done() && std::chrono::steady_clock::now() < deadline) {
            pump();
            std::this_thread::sleep_for(5ms);
        }
        return done();
    }

    static int timedOutHops()
    {
        auto& s = state();
        std::lock_guard<std::mutex> lock(s.mutex);
        return s.timedOutHops;
    }

private:
    struct Hop
    {
        std::function<void()> fn;
        bool done = false;
    };

    struct State
    {
        std::mutex mutex;
        std::condition_variable changed;
        std::deque<std::shared_ptr<Hop>> queue;
        std::thread::id mainThread;
        int timedOutHops = 0;
    };

    static State& state()
    {
        static State s;
        return s;
    }

    static bool isMainThread()
    {
        auto& s = state();
        std::lock_guard<std::mutex> lock(s.mutex);
        return std::this_thread::get_id() == s.mainThread;
    }

    static void invoke(std::function<void()>&& fn, bool blocking)
    {
        if (blocking && isMainThread()) {
            fn();
            return;
        }

        auto& s = state();
        auto hop = std::make_shared<Hop>();
        hop->fn = std::move(fn);
        std::unique_lock<std::mutex> lock(s.mutex);
        s.queue.push_back(hop);
        if (!blocking) {
            return;
        }
        if (s.changed.wait_for(lock, hopTimeout, [&hop] { return hop->done; })) {
            return;
        }
        if (const auto it = std::ranges::find(s.queue, hop); it != s.queue.end()) {
            // The main thread never got to it: count it and run it here instead
            s.queue.erase(it);
            ++s.timedOutHops;
            lock.unlock();
            hop->fn();
            return;
        }
        // The main thread is running it right now
        s.changed.wait(lock, [&hop] { return hop->done; });
    }
};

}  // namespace

class AsyncRecomputeTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        _docName = App::GetApplication().getUniqueDocumentName("async_recompute");
        _doc = App::GetApplication().newDocument(_docName.c_str(), "testUser");
    }

    void TearDown() override
    {
        if (!_docName.empty() && App::GetApplication().getDocument(_docName.c_str())) {
            App::GetApplication().closeDocument(_docName.c_str());
        }
    }

    std::string _docName;
    App::Document* _doc {};
};

TEST_F(AsyncRecomputeTest, CloseDocumentWaitsForInFlightAsyncRecompute)
{
    auto* object = dynamic_cast<App::FeatureTestAsyncBlocker*>(
        _doc->addObject("App::FeatureTestAsyncBlocker", "BlockingFeature")
    );
    ASSERT_NE(object, nullptr);

    App::FeatureTestAsyncBlocker::resetBlocker();
    BOOST_SCOPE_EXIT_ALL(&)
    {
        App::FeatureTestAsyncBlocker::releaseBlocker();
    };

    object->touch();

    App::GetApplication().queueRecomputeRequest(App::RecomputeRequest::fromDocumentObject(*object));

    ASSERT_TRUE(App::FeatureTestAsyncBlocker::waitUntilStarted(2s));

    auto closeFuture = std::async(std::launch::async, [this] {
        return App::GetApplication().closeDocument(_docName.c_str());
    });

    EXPECT_EQ(closeFuture.wait_for(50ms), std::future_status::timeout);

    App::FeatureTestAsyncBlocker::releaseBlocker();

    ASSERT_EQ(closeFuture.wait_for(2s), std::future_status::ready);
    EXPECT_TRUE(closeFuture.get());

    _doc = nullptr;
}

TEST_F(AsyncRecomputeTest, WorkerSafetyIsCheckedFromRequest)
{
    auto* safeObject = dynamic_cast<App::FeatureTest*>(
        _doc->addObject("App::FeatureTest", "SafeFeature")
    );
    auto* unsafeObject = dynamic_cast<App::FeatureTestAttribute*>(
        _doc->addObject("App::FeatureTestAttribute", "UnsafeFeature")
    );

    ASSERT_NE(safeObject, nullptr);
    ASSERT_NE(unsafeObject, nullptr);

    EXPECT_TRUE(
        App::GetApplication().canRecomputeRequestOnWorker(
            App::RecomputeRequest::fromDocumentObject(*safeObject)
        )
    );
    EXPECT_FALSE(
        App::GetApplication().canRecomputeRequestOnWorker(
            App::RecomputeRequest::fromDocumentObject(*unsafeObject)
        )
    );
    EXPECT_FALSE(
        App::GetApplication().canRecomputeRequestOnWorker(App::RecomputeRequest::fromDocument(*_doc))
    );
}

// The hooks are installed from another module (Gui, or this test), so they must
// reach the signals FreeCADApp emits. As inline statics they didn't on Windows,
// and the worker ran the GUI's document slots on its own thread.
TEST_F(AsyncRecomputeTest, WorkerSignalsRunOnTheMainThread)
{
    FakeMainThread mainThread;

    auto* object = dynamic_cast<App::FeatureTestAsyncBlocker*>(
        _doc->addObject("App::FeatureTestAsyncBlocker", "BlockingFeature")
    );
    ASSERT_NE(object, nullptr);

    std::thread::id slotThread;
    std::atomic<bool> fired {false};
    _doc->signalRecomputedObject.connect([&](const App::DocumentObject&) {
        slotThread = std::this_thread::get_id();
        fired = true;
    });

    App::FeatureTestAsyncBlocker::resetBlocker();
    App::FeatureTestAsyncBlocker::releaseBlocker();
    object->touch();
    App::GetApplication().queueRecomputeRequest(App::RecomputeRequest::fromDocumentObject(*object));

    ASSERT_TRUE(FakeMainThread::pumpUntil([&fired] { return fired.load(); }, 5000ms));
    EXPECT_EQ(slotThread, std::this_thread::get_id());
}

// With the GUI the worker hands its document signals to the main thread and
// waits for them. A close on the main thread used to wait for the worker in
// turn, so the two waited on each other and the GUI froze.
TEST_F(AsyncRecomputeTest, CloseOnTheMainThreadDoesNotWaitForTheWorker)
{
    FakeMainThread mainThread;

    auto* object = dynamic_cast<App::FeatureTestAsyncBlocker*>(
        _doc->addObject("App::FeatureTestAsyncBlocker", "BlockingFeature")
    );
    ASSERT_NE(object, nullptr);

    App::FeatureTestAsyncBlocker::resetBlocker();
    BOOST_SCOPE_EXIT_ALL(&)
    {
        App::FeatureTestAsyncBlocker::releaseBlocker();
    };

    object->touch();
    App::GetApplication().queueRecomputeRequest(App::RecomputeRequest::fromDocumentObject(*object));
    // The worker hands signals to the main thread on its way in, so keep pumping
    ASSERT_TRUE(
        FakeMainThread::pumpUntil([] { return App::FeatureTestAsyncBlocker::waitUntilStarted(0ms); }, 2000ms)
    );

    auto releaser = std::async(std::launch::async, [] {
        std::this_thread::sleep_for(200ms);
        App::FeatureTestAsyncBlocker::releaseBlocker();
    });

    const auto start = std::chrono::steady_clock::now();
    App::GetApplication().closeDocument(_docName.c_str());
    const auto elapsed = std::chrono::steady_clock::now() - start;

    EXPECT_LT(elapsed, 1s);
    EXPECT_TRUE(
        FakeMainThread::pumpUntil(
            [this] { return !App::GetApplication().getDocument(_docName.c_str()); },
            5000ms
        )
    );
    EXPECT_EQ(FakeMainThread::timedOutHops(), 0);
    releaser.wait();
    _doc = nullptr;
}

// A long recompute processes events, so a timer or a queued call can close the
// document from inside its own recompute. That used to delete the document
// under the recompute still running on the stack.
TEST_F(AsyncRecomputeTest, CloseFromInsideTheRecomputeWaitsForItToFinish)
{
    FakeMainThread mainThread;

    for (const char* name : {"First", "Second", "Third"}) {
        _doc->addObject("App::FeatureTest", name)->touch();
    }

    int recomputed = 0;
    bool closeReturned = true;
    bool openDuringRecompute = false;
    _doc->signalRecomputedObject.connect([&](const App::DocumentObject&) {
        if (++recomputed == 1) {
            closeReturned = App::GetApplication().closeDocument(_docName.c_str());
        }
    });
    _doc->signalRecomputed.connect([&](const App::Document&, const std::vector<App::DocumentObject*>&) {
        openDuringRecompute = App::GetApplication().getDocument(_docName.c_str()) != nullptr;
    });

    _doc->recompute();

    EXPECT_FALSE(closeReturned);
    EXPECT_TRUE(openDuringRecompute);
    ASSERT_NE(App::GetApplication().getDocument(_docName.c_str()), nullptr);
    // The pending close stops the recompute at the next object
    EXPECT_EQ(recomputed, 1);
    EXPECT_TRUE(
        FakeMainThread::pumpUntil(
            [this] { return !App::GetApplication().getDocument(_docName.c_str()); },
            2000ms
        )
    );
    _doc = nullptr;
}

// Without an event loop (no GUI) there is nothing to hand the close to, so it
// is refused and the recompute carries on.
TEST_F(AsyncRecomputeTest, CloseFromInsideTheRecomputeIsRefusedWithoutAnEventLoop)
{
    for (const char* name : {"First", "Second", "Third"}) {
        _doc->addObject("App::FeatureTest", name)->touch();
    }

    int recomputed = 0;
    bool closeReturned = true;
    _doc->signalRecomputedObject.connect([&](const App::DocumentObject&) {
        if (++recomputed == 1) {
            closeReturned = App::GetApplication().closeDocument(_docName.c_str());
        }
    });

    _doc->recompute();

    EXPECT_FALSE(closeReturned);
    ASSERT_NE(App::GetApplication().getDocument(_docName.c_str()), nullptr);
    EXPECT_EQ(recomputed, 3);
    EXPECT_FALSE(_doc->testStatus(App::Document::Recomputing));
}

// closeAllDocuments() used to loop until the map was empty, so a document that
// can't close yet must not make it spin.
TEST_F(AsyncRecomputeTest, CloseAllDocumentsFromInsideARecomputeLeavesThatDocumentOpen)
{
    for (const char* name : {"First", "Second"}) {
        _doc->addObject("App::FeatureTest", name)->touch();
    }

    int recomputed = 0;
    _doc->signalRecomputedObject.connect([&](const App::DocumentObject&) {
        if (++recomputed == 1) {
            App::GetApplication().closeAllDocuments();
        }
    });

    _doc->recompute();

    ASSERT_NE(App::GetApplication().getDocument(_docName.c_str()), nullptr);
    EXPECT_EQ(recomputed, 2);
}
