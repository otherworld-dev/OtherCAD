// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>
#include <gmock/gmock.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "App/Application.h"
#include "App/Document.h"
#include "App/FeatureTest.h"
#include "App/MergeDocuments.h"
#include "App/StringHasher.h"
#include "Base/Console.h"
#include "Base/Writer.h"
#include <src/App/InitApplication.h>

using ::testing::Eq;
using ::testing::Ne;

// NOLINTBEGIN(readability-magic-numbers)

class FakeWriter: public Base::Writer
{
    void writeFiles() override
    {}
    std::ostream& Stream() override
    {
        return std::cout;
    }
};

class DocumentTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        _docName = App::GetApplication().getUniqueDocumentName("test");
        _doc = App::GetApplication().newDocument(_docName.c_str(), "testUser");
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(_docName.c_str());
    }

    App::Document* doc()
    {
        return _doc;
    }

private:
    std::string _docName;
    App::Document* _doc {};
};


TEST_F(DocumentTest, addStringHasherIndicatesUnwrittenWhenNew)
{
    // Arrange
    App::StringHasherRef hasher(new App::StringHasher);

    // Act
    auto addResult = doc()->addStringHasher(hasher);

    // Assert
    EXPECT_TRUE(addResult.first);
    EXPECT_THAT(addResult.second, Ne(-1));
}

TEST_F(DocumentTest, addStringHasherIndicatesAlreadyWritten)
{
    // Arrange
    App::StringHasherRef hasher(new App::StringHasher);
    doc()->addStringHasher(hasher);

    // Act
    auto addResult = doc()->addStringHasher(hasher);

    // Assert
    EXPECT_FALSE(addResult.first);
}

TEST_F(DocumentTest, getStringHasherGivesExpectedHasher)
{
    // Arrange
    App::StringHasherRef hasher(new App::StringHasher);
    auto pair = doc()->addStringHasher(hasher);
    int index = pair.second;

    // Act
    auto foundHasher = doc()->getStringHasher(index);

    // Assert
    EXPECT_EQ(hasher, foundHasher);
}

TEST_F(DocumentTest, importObjectsRestoresSourceStringHasher)
{
    // Arrange
    auto& app = App::GetApplication();
    const std::string sourceName = app.getUniqueDocumentName("MergeSource");
    App::Document* source = app.newDocument(sourceName.c_str(), "testUser");
    App::StringHasherRef sourceHasher = source->getStringHasher();
    ASSERT_TRUE(sourceHasher);
    sourceHasher->setSaveAll(true);
    sourceHasher->getID("persisted element name");

    const std::string path = App::Application::getTempFileName();
    ASSERT_TRUE(source->saveAs(path.c_str()));
    const std::string savedPath = source->getFileName();
    app.closeDocument(sourceName.c_str());

    std::size_t restoredStringCount = 0;
    auto connection = doc()->signalFinishImportObjects.connect(
        [this, &restoredStringCount](const std::vector<App::DocumentObject*>&) {
            App::StringHasherRef importedHasher = doc()->getStringHasher(0);
            restoredStringCount = importedHasher ? importedHasher->size() : 0;
        }
    );

    // Act
    std::ifstream stream(savedPath, std::ios::in | std::ios::binary);
    ASSERT_TRUE(stream.is_open());
    App::MergeDocuments merge(doc());
    merge.importObjects(stream);

    // Assert
    EXPECT_GT(restoredStringCount, 0);
    connection.disconnect();
    std::remove(savedPath.c_str());
}

namespace
{

// Collects the warnings sent to the console while it is alive
class WarningCollector final: public Base::ILogger
{
public:
    WarningCollector()
    {
        Base::Console().attachObserver(this);
    }
    ~WarningCollector() override
    {
        Base::Console().detachObserver(this);
    }
    WarningCollector(const WarningCollector&) = delete;
    WarningCollector& operator=(const WarningCollector&) = delete;

    void sendLog(
        const std::string& /*notifiername*/,
        const std::string& msg,
        Base::LogStyle level,
        Base::IntendedRecipient /*recipient*/,
        Base::ContentType /*content*/
    ) override
    {
        if (level == Base::LogStyle::Warning) {
            std::lock_guard<std::mutex> lock(mutex);
            warnings.push_back(msg);
        }
    }

    const char* name() override
    {
        return "WarningCollector";
    }

    int count(const std::string& text)
    {
        std::lock_guard<std::mutex> lock(mutex);
        return static_cast<int>(std::ranges::count_if(warnings, [&text](const std::string& msg) {
            return msg.find(text) != std::string::npos;
        }));
    }

private:
    std::mutex mutex;
    std::vector<std::string> warnings;
};

}  // namespace

TEST_F(DocumentTest, aLongRecomputeWarnsOnceWhileItIsStillRunning)
{
    // A recompute that runs for minutes looks like a stuck Recomputing flag from outside
    // (#1007). Past RecomputeWarnSeconds it says so once, naming where it has got to.
    auto hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Document"
    );
    hGrp->SetFloat("RecomputeWarnSeconds", 0.05);

    auto* slow = doc()->addObject("App::FeatureTestAsyncBlocker", "Slow");
    auto* after = doc()->addObject("App::FeatureTest", "After");
    auto* last = doc()->addObject("App::FeatureTest", "Last");
    ASSERT_NE(slow, nullptr);
    slow->touch();
    after->touch();
    last->touch();

    App::FeatureTestAsyncBlocker::resetBlocker();
    std::thread releaser([] {
        std::this_thread::sleep_for(std::chrono::milliseconds(150));
        App::FeatureTestAsyncBlocker::releaseBlocker();
    });

    int warnings = 0;
    {
        WarningCollector collector;
        doc()->recompute();
        warnings = collector.count("has been recomputing");
    }
    releaser.join();
    EXPECT_EQ(warnings, 1);

    // A quick recompute under the default threshold stays quiet
    hGrp->RemoveFloat("RecomputeWarnSeconds");
    App::FeatureTestAsyncBlocker::releaseBlocker();
    slow->touch();
    after->touch();
    {
        WarningCollector collector;
        doc()->recompute();
        warnings = collector.count("has been recomputing");
    }
    EXPECT_EQ(warnings, 0);
}

// NOLINTEND(readability-magic-numbers)
